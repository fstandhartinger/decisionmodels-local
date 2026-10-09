"""Resumable Hugging Face downloads with strict size and SHA-256 checks."""
import concurrent.futures
import hashlib
import os
import re
import shutil
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

_print_lock = threading.Lock()
CHUNK = 1024 * 1024


class _DownloadRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        target = urllib.parse.urlparse(newurl)
        if target.scheme != "https":
            raise urllib.error.URLError("model download redirect must use HTTPS")
        redirected = super().redirect_request(request, fp, code, msg, headers, newurl)
        if redirected is not None and target.netloc != urllib.parse.urlparse(request.full_url).netloc:
            redirected.remove_header("Authorization")
        return redirected


def _download_open(request, timeout=60):
    return urllib.request.build_opener(_DownloadRedirect()).open(request, timeout=timeout)


def hf_url(repo, revision, remote_path):
    endpoint = os.environ.get("HF_ENDPOINT", "https://huggingface.co").rstrip("/")
    if not endpoint.startswith("https://"):
        raise ValueError("HF_ENDPOINT must use HTTPS")
    parts = [urllib.parse.quote(repo, safe="/-._~"), urllib.parse.quote("resolve", safe="-._~"), urllib.parse.quote(revision, safe="-._~")]
    file_parts = "/".join(urllib.parse.quote(p, safe="-._~") for p in Path(remote_path).parts)
    return endpoint + "/" + "/".join(parts) + "/" + file_parts


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _free_bytes(path):
    path.mkdir(parents=True, exist_ok=True)
    return shutil.disk_usage(path).free


def verify_file(path, size, sha256):
    if not path.exists() or path.stat().st_size != size:
        return False
    return sha256_file(path) == sha256


def _download_one(spec, target, repo, revision, opener=_download_open, retries=4):
    path_value = str(spec.get("path", ""))
    if not path_value or "\\" in path_value or Path(path_value).is_absolute() or ".." in Path(path_value).parts:
        raise OSError("unsafe relative download path")
    target.parent.mkdir(parents=True, exist_ok=True)
    try: target.resolve().relative_to(target.parents[len(Path(spec["path"]).parts) - 1].resolve())
    except (ValueError, IndexError): raise OSError("weight target escapes the model directory")
    if verify_file(target, spec["size"], spec["sha256"]):
        return target
    partial = target.with_name(target.name + ".part")
    base = target.parents[len(Path(spec["path"]).parts) - 1]
    try:
        target.resolve().relative_to(base.resolve())
        partial.resolve().relative_to(base.resolve())
    except (ValueError, IndexError): raise OSError("weight target escapes the model directory")
    url = hf_url(repo, revision, spec["path"])
    token = os.environ.get("HF_TOKEN")
    if partial.exists() and partial.stat().st_size >= spec["size"]:
        if verify_file(partial, spec["size"], spec["sha256"]):
            os.replace(partial, target)
            return target
        partial.unlink()
    for attempt in range(retries):
        offset = partial.stat().st_size if partial.exists() else 0
        headers = {"User-Agent": "dm-local/0.1"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        if token:
            headers["Authorization"] = "Bearer " + token
        request = urllib.request.Request(url, headers=headers)
        try:
            response = opener(request, timeout=60)
            status = getattr(response, "status", response.getcode())
            if offset and status != 206:
                response.close()
                partial.unlink(missing_ok=True)
                offset = 0
                response = opener(urllib.request.Request(url, headers={k: v for k, v in headers.items() if k != "Range"}), timeout=60)
                status = getattr(response, "status", response.getcode())
            if status not in (200, 206):
                raise OSError(f"unexpected HTTP status {status}")
            mode = "ab" if status == 206 and offset else "wb"
            downloaded = offset if mode == "ab" else 0
            with response, partial.open(mode) as out:
                while True:
                    chunk = response.read(CHUNK)
                    if not chunk:
                        break
                    out.write(chunk)
                    downloaded += len(chunk)
                    percent = min(100, int(downloaded * 100 / max(spec["size"], 1)))
                    with _print_lock:
                        print(f"\rDownloading {spec['path']}: {percent}% ({downloaded}/{spec['size']} bytes)",
                              end="", file=sys.stderr, flush=True)
                out.flush()
                os.fsync(out.fileno())
            if partial.stat().st_size != spec["size"]:
                raise OSError(f"size mismatch for {spec['path']}: expected {spec['size']}, got {partial.stat().st_size}")
            if not verify_file(partial, spec["size"], spec["sha256"]):
                partial.unlink(missing_ok=True)
                raise OSError(f"SHA-256 mismatch for {spec['path']}; partial file removed")
            os.replace(partial, target)
            with _print_lock:
                print(file=sys.stderr, flush=True)
            return target
        except (OSError, urllib.error.URLError, TimeoutError) as exc:
            # Exceptions from HTTP libraries can include request URLs but not headers;
            # the HF token is only ever set in Authorization and is never printed.
            if attempt + 1 == retries:
                raise OSError(f"download failed for {spec['path']}: {exc}") from exc
            time.sleep(min(2 ** attempt, 8))
    raise OSError(f"download failed for {spec['path']}")


def download_variant(model, variant, state_root, opener=_download_open):
    files = variant.get("files", [])
    required = sum(int(spec["size"]) for spec in files)
    destination = Path(state_root) / "models" / model["slug"]
    free = _free_bytes(destination)
    needed = int(required * 1.1)
    if free < needed:
        raise OSError(f"insufficient disk space: need {needed} bytes including 10% margin, have {free} bytes")
    revision = model.get("weights", {}).get("revision")
    if not revision:
        raise ValueError("catalog entry has no pinned Hugging Face revision")
    return download_files(files, model["weights"]["repo"], revision, destination, opener=opener)


def download_files(files, repo, revision, destination, opener=_download_open):
    """Download and verify a file list from a pinned HF repo into destination."""
    destination = Path(destination)
    required = sum(int(spec["size"]) for spec in files)
    destination.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(destination).free < int(required * 1.1):
        raise OSError(f"insufficient disk space: need {int(required * 1.1)} bytes including 10% margin")
    def run(spec):
        value = str(spec.get("path", ""))
        if not value or "\\" in value or Path(value).is_absolute() or ".." in Path(value).parts:
            raise OSError("unsafe relative download path")
        target = destination.joinpath(*Path(value).parts)
        return _download_one(spec, target, repo, revision, opener=opener)
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, max(1, len(files)))) as pool:
        return list(pool.map(run, files))
