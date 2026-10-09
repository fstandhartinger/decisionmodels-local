"""Acquire the pinned uv binary without using a shell installer."""
import os
import platform
import shutil
import subprocess
import tarfile
import urllib.request
import zipfile
from pathlib import Path

from .pins import UV_ASSETS, UV_RELEASE, UV_VERSION
from .storage import sha256_file


def uv_platform_key():
    machine = platform.machine().lower()
    osname = platform.system().lower()
    arch = "aarch64" if machine in ("aarch64", "arm64") else "x86_64" if machine in ("x86_64", "amd64") else machine
    if osname == "linux": suffix = "unknown-linux-gnu"
    elif osname == "darwin": suffix = "apple-darwin"
    elif osname == "windows": suffix = "pc-windows-msvc"
    else: raise RuntimeError(f"uv is not pinned for {osname}/{machine}")
    key = f"{arch}-{suffix}"
    if key not in UV_ASSETS: raise RuntimeError(f"uv is not pinned for {key}")
    return key


def ensure_uv(state_root, opener=urllib.request.urlopen):
    existing = shutil.which("uv")
    if existing:
        version = subprocess.run([existing, "--version"], capture_output=True, text=True).stdout.strip()
        if version == "uv " + UV_VERSION:
            return Path(existing)
    root = Path(state_root) / "runtimes" / ("uv-" + UV_VERSION)
    binary = root / ("uv.exe" if os.name == "nt" else "uv")
    if binary.exists(): return binary
    pin = UV_ASSETS[uv_platform_key()]
    archive = root.with_suffix(".download")
    root.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(UV_RELEASE + "/" + pin["file"], headers={"User-Agent": "dm-local"})
    with opener(request, timeout=60) as response, archive.open("wb") as out:
        shutil.copyfileobj(response, out)
    digest = sha256_file(archive)
    if digest != pin["sha256"]:
        archive.unlink(missing_ok=True)
        raise RuntimeError("downloaded uv binary failed SHA-256 verification")
    if pin["file"].endswith(".zip"):
        with zipfile.ZipFile(archive) as zf:
            members = [m for m in zf.namelist() if m.endswith("/uv.exe") or m == "uv.exe"]
            if not members: raise RuntimeError("pinned uv archive contains no uv.exe")
            with zf.open(members[0]) as src, binary.open("wb") as dst: shutil.copyfileobj(src, dst)
    else:
        with tarfile.open(archive, "r:gz") as tf:
            members = [m for m in tf.getmembers() if Path(m.name).name == "uv" and m.isfile()]
            if not members: raise RuntimeError("pinned uv archive contains no uv executable")
            stream = tf.extractfile(members[0])
            if stream is None: raise RuntimeError("unable to read pinned uv binary")
            with stream, binary.open("wb") as dst: shutil.copyfileobj(stream, dst)
        try: binary.chmod(0o755)
        except OSError: pass
    archive.unlink(missing_ok=True)
    return binary
