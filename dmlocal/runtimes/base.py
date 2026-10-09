"""Shared runtime helpers."""
import json
import os
import shlex
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from ..paths import ensure_state
from ..process import read_process, start_process, stop_process


class Runtime:
    def __init__(self, model, variant, root=None, port=8741):
        self.model = model
        self.variant = variant
        self.root = Path(root or ensure_state())
        self.port = int(port)
        self.slug = model["slug"]
        self.name = "dm-local-" + self.slug
        self.weights = self.root / "models" / self.slug
        self.runtime_dir = self.root / "runtimes" / (self.slug + "-" + variant["id"])

    def prepare(self): raise NotImplementedError
    def start(self): raise NotImplementedError
    def stop(self): raise NotImplementedError

    def health(self):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health", timeout=2) as response:
                return response.status == 200
        except (OSError, urllib.error.URLError):
            return False

    def _serve_command(self, port=None):
        serve = self.variant.get("serve", {})
        command = serve.get("command")
        if isinstance(command, list):
            args = [str(x) for x in command]
        elif isinstance(command, str):
            args = shlex.split(command)
        else:
            raise RuntimeError(f"catalog variant {self.variant['id']} has no runnable serve command")
        if args and args[0].lower() in ("sh", "bash", "cmd", "powershell", "pwsh") and "-c" in args:
            raise RuntimeError("catalog serve commands may not invoke a shell with -c")
        replacements = {"{port}": str(port or self.port), "{weights}": str(self.weights),
                        "{model_dir}": str(self.weights), "{slug}": self.slug}
        for index, arg in enumerate(args):
            for key, value in replacements.items():
                arg = arg.replace(key, value)
            if arg.startswith("--host="):
                host = arg.split("=", 1)[1]
                if host != "127.0.0.1":
                    raise RuntimeError("model backend must bind to 127.0.0.1")
            args[index] = "127.0.0.1" if arg == "0.0.0.0" else arg
        if "--host" not in args and not any(arg.startswith("--host=") for arg in args) and self.variant.get("serve", {}).get("bind_address") != "127.0.0.1":
            raise RuntimeError("catalog serve command must explicitly bind the backend to 127.0.0.1")
        if "--host" in args:
            index = args.index("--host")
            if index + 1 >= len(args) or args[index + 1] != "127.0.0.1":
                raise RuntimeError("model backend must bind to 127.0.0.1")
        if not args:
            raise RuntimeError("empty serve command")
        # Resolve an explicit script path inside the downloaded weight tree. Do not use a shell.
        for index, arg in enumerate(args):
            candidate = Path(arg)
            if candidate.suffix in (".py", ".sh"):
                path = (self.weights / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
                try: path.relative_to(self.weights.resolve())
                except ValueError as exc: raise RuntimeError("serve script must stay inside the downloaded model directory") from exc
                if not path.is_file(): raise RuntimeError(f"catalog serve script is missing: {candidate}")
                args[index] = str(path)
                break
        return args

    def _install_packages(self, packages, python=None, extra_index_urls=None):
        if not packages:
            return None
        from ..uv import ensure_uv
        uv = ensure_uv(self.root)
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        venv = self.runtime_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        env = os.environ.copy()
        env.pop("HF_TOKEN", None)
        if not venv.exists():
            requested_python = python or sys.executable
            subprocess.run([str(uv), "venv", str(self.runtime_dir), "--python", requested_python], check=True, env=env)
        args = [str(uv), "pip", "install", "--python", str(venv)]
        for url in extra_index_urls or []: args.extend(["--extra-index-url", str(url)])
        args.extend(str(pkg) for pkg in packages)
        subprocess.run(args, check=True, env=env)
        return str(venv)

    def _wait_ready(self, seconds=45):
        import time
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self.health(): return True
            time.sleep(0.5)
        return False

    def _process_start(self, process_name, command, cwd=None, env=None):
        return start_process(self.root, process_name, command, cwd=cwd, env=env)

    def _process_stop(self, process_name):
        return stop_process(self.root, process_name)

    def _process_status(self, process_name):
        return read_process(self.root, process_name)

    @staticmethod
    def _run(args, check=True):
        return subprocess.run(args, check=check, text=True, capture_output=True)
