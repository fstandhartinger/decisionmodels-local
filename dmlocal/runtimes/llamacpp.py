"""llama.cpp runtime. Refuses until a platform asset has a reviewed SHA-256 pin."""
import os
import platform
import shutil
import subprocess
import tarfile
import urllib.request
import zipfile
from pathlib import Path

from .base import Runtime
from ..pins import LLAMA_CPP_ASSETS, require_llama_asset
from ..storage import sha256_file


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
        if asset.suffix == ".zip":
            with zipfile.ZipFile(asset) as archive:
                member = next((m for m in archive.namelist() if Path(m).name == ("llama-server.exe" if os.name == "nt" else "llama-server")), None)
                if not member: raise RuntimeError("pinned llama.cpp archive contains no llama-server")
                with archive.open(member) as src, (self.runtime_dir / Path(member).name).open("wb") as dst: shutil.copyfileobj(src, dst)
        else:
            with tarfile.open(asset, "r:*") as archive:
                member = next((m for m in archive.getmembers() if Path(m.name).name == ("llama-server.exe" if os.name == "nt" else "llama-server") and m.isfile()), None)
                if not member: raise RuntimeError("pinned llama.cpp archive contains no llama-server")
                stream = archive.extractfile(member)
                if stream is None: raise RuntimeError("unable to read llama-server from verified archive")
                binary = self.runtime_dir / Path(member.name).name
                with stream, binary.open("wb") as dst: shutil.copyfileobj(stream, dst)
                try: binary.chmod(0o755)
                except OSError: pass
        self.binary = self.runtime_dir / ("llama-server.exe" if os.name == "nt" else "llama-server")

    def start(self):
        gguf = next((self.weights / f["path"] for f in self.variant.get("files", []) if str(f["path"]).lower().endswith(".gguf")), None)
        if gguf is None or not gguf.is_file(): raise RuntimeError("catalog variant has no downloaded GGUF model file")
        command = [str(self.binary), "-m", str(gguf), "--host", "127.0.0.1", "--port", str(self.port)]
        mmproj = next((self.weights / f["path"] for f in self.variant.get("files", []) if "mmproj" in str(f["path"]).lower()), None)
        if mmproj: command.extend(["--mmproj", str(mmproj)])
        command.extend(self.variant.get("serve", {}).get("extra_args", []))
        return self._process_start(self.name + "-backend", command, cwd=self.weights)

    def stop(self): return self._process_stop(self.name + "-backend")
