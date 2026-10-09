"""llama.cpp runtime. Refuses until a platform asset has a reviewed SHA-256 pin."""
import os
import platform
import re
import shutil
import subprocess
import tarfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

from .base import Runtime
from ..pins import LLAMA_CPP_ASSETS, require_llama_asset
from ..storage import sha256_file


def _safe_extract_tar(archive_path, extracted):
    """Extract regular files and only relative symlinks that stay in the archive root."""
    extracted = Path(extracted).resolve()
    extracted.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "r:*") as archive:
        members = archive.getmembers()
        by_name = {}
        symlinks = {}
        for member in members:
            if "\\" in member.name:
                raise RuntimeError("pinned llama.cpp archive contains a path with Windows separators")
            name = PurePosixPath(member.name)
            if (name.is_absolute() or (name.parts and re.match(r"^[A-Za-z]:", name.parts[0]))
                    or any(part in ("", ".", "..") for part in name.parts)):
                raise RuntimeError("pinned llama.cpp archive contains an unsafe path")
            key = name.as_posix().rstrip("/")
            if not key or key in by_name:
                raise RuntimeError("pinned llama.cpp archive contains a duplicate or empty path")
            by_name[key] = (member, name)
            if member.issym():
                link = PurePosixPath(member.linkname)
                if link.is_absolute() or "\\" in member.linkname or (link.parts and re.match(r"^[A-Za-z]:", link.parts[0])):
                    raise RuntimeError("pinned llama.cpp archive contains an absolute symlink")
                resolved = list(name.parent.parts)
                for part in link.parts:
                    if part in ("", "."):
                        continue
                    if part == "..":
                        if not resolved:
                            raise RuntimeError("pinned llama.cpp archive symlink escapes its extraction root")
                        resolved.pop()
                    else:
                        resolved.append(part)
                if not resolved:
                    raise RuntimeError("pinned llama.cpp archive symlink targets the extraction root")
                symlinks[key] = (member, name)
            elif not (member.isdir() or member.isfile()):
                raise RuntimeError("pinned llama.cpp archive contains a hard link or unsupported special file")

        for key in symlinks:
            prefix = key + "/"
            if any(other.startswith(prefix) for other in by_name if other != key):
                raise RuntimeError("pinned llama.cpp archive uses a symlink as a parent path")

        for key, (member, name) in by_name.items():
            if key in symlinks:
                continue
            target = extracted.joinpath(*name.parts)
            target.resolve().relative_to(extracted)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise RuntimeError("unable to read regular file from pinned llama.cpp archive")
            with source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            try:
                target.chmod(0o755 if member.mode & 0o111 else 0o644)
            except OSError:
                pass

        for member, name in symlinks.values():
            target = extracted.joinpath(*name.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            os.symlink(member.linkname, target)


def platform_key(variant):
    osname = platform.system().lower()
    arch = platform.machine().lower()
    if osname == "linux" and arch in ("x86_64", "amd64"):
        return "linux-x86_64-" + str(variant.get("accelerator", "cpu")).lower()
    if osname == "darwin" and arch in ("arm64", "aarch64"):
        return "macos-arm64-metal"
    if osname == "windows" and arch in ("x86_64", "amd64"):
        return "windows-x86_64-" + str(variant.get("accelerator", "cpu")).lower()
    raise RuntimeError(f"llama.cpp runtime has no verified binary pin for {osname}/{arch}")


class LlamaCppRuntime(Runtime):
    def prepare(self):
        key = platform_key(self.variant)
        pin = require_llama_asset(key)
        asset = self.runtime_dir / pin["file"]
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        if not asset.exists():
            with urllib.request.urlopen(pin["url"], timeout=60) as response, asset.open("wb") as out:
                shutil.copyfileobj(response, out)
        digest = sha256_file(asset)
        if digest != pin["sha256"]:
            asset.unlink(missing_ok=True)
            raise RuntimeError("llama.cpp asset failed SHA-256 verification")
        extracted = self.runtime_dir / "unpacked"
        if extracted.exists():
            shutil.rmtree(extracted)
        extracted.mkdir(parents=True)
        binary_name = "llama-server.exe" if os.name == "nt" else "llama-server"
        if asset.suffix == ".zip":
            with zipfile.ZipFile(asset) as archive:
                for member in archive.infolist():
                    if "\\" in member.filename:
                        raise RuntimeError("pinned llama.cpp archive contains a path with Windows separators")
                    name = PurePosixPath(member.filename)
                    mode = (member.external_attr >> 16) & 0o170000
                    if name.is_absolute() or (name.parts and name.parts[0].endswith(":")) or any(part in ("", ".", "..") for part in name.parts) or mode == 0o120000:
                        raise RuntimeError("pinned llama.cpp archive contains an unsafe path or link")
                    target = extracted.joinpath(*name.parts)
                    target.resolve().relative_to(extracted.resolve())
                    if member.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(member) as source, target.open("wb") as output:
                        shutil.copyfileobj(source, output)
        else:
            _safe_extract_tar(asset, extracted)
        binaries = [path for path in extracted.rglob(binary_name) if path.is_file()]
        if not binaries:
            raise RuntimeError("pinned llama.cpp archive contains no llama-server")
        self.binary = binaries[0]

    def start(self):
        gguf = next((self.weights / f["path"] for f in self.variant.get("files", []) if str(f["path"]).lower().endswith(".gguf")), None)
        if gguf is None or not gguf.is_file(): raise RuntimeError("catalog variant has no downloaded GGUF model file")
        command = [str(self.binary), "-m", str(gguf), "--host", "127.0.0.1", "--port", str(self.port)]
        mmproj = next((self.weights / f["path"] for f in self.variant.get("files", []) if "mmproj" in str(f["path"]).lower()), None)
        if mmproj: command.extend(["--mmproj", str(mmproj)])
        command.extend(self.variant.get("serve", {}).get("extra_args", []))
        return self._process_start(self.name + "-backend", command, cwd=self.weights)

    def stop(self): return self._process_stop(self.name + "-backend")
