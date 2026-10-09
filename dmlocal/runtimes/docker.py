"""Pinned Docker runtime. Container names are exact and model-specific."""
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

from .base import Runtime
from ..pins import require_docker_image


class DockerRuntime(Runtime):
    def _compose_files(self):
        serve = self.variant.get("serve", {})
        files = serve.get("compose_files") or []
        resolved = []
        for value in files:
            path = (self.weights / value).resolve()
            try: path.relative_to(self.weights.resolve())
            except ValueError as exc: raise RuntimeError("compose files must stay inside the model directory") from exc
            if not path.is_file(): raise RuntimeError(f"compose file is missing: {value}")
            text = path.read_text(encoding="utf-8")
            if re.search(r"(?m)^\s*build\s*:", text):
                raise RuntimeError("compose bundles with build steps are not supported; only pinned image pulls are allowed")
            if re.search(r"(?m)^\s*network_mode\s*:\s*['\"]?host", text):
                raise RuntimeError("compose bundles using host networking are not supported")
            lines = text.splitlines()
            index = 0
            while index < len(lines):
                match = re.match(r"^(\s*)ports\s*:\s*.*$", lines[index])
                if not match:
                    index += 1
                    continue
                indent = len(match.group(1))
                index += 1
                while index < len(lines):
                    line = lines[index]
                    if line.strip() and len(line) - len(line.lstrip()) <= indent:
                        break
                    value = line.strip().lstrip("-").strip().strip("\"'")
                    if value and not value.startswith("#") and not value.startswith("host_ip:"):
                        if not value.startswith("127.0.0.1:"):
                            raise RuntimeError("compose host ports must bind explicitly to 127.0.0.1")
                    index += 1
            for image in re.findall(r"(?m)^\s*image:\s*['\"]?([^\s'\"]+)", text):
                require_docker_image(image)
            resolved.append(path)
        return resolved

    def _compose_command(self, validate=True):
        command = ["docker", "compose", "-p", self.name]
        if validate:
            paths = self._compose_files()
        else:
            paths = []
            for value in self.variant.get("serve", {}).get("compose_files", []):
                path = (self.weights / value).resolve()
                try: path.relative_to(self.weights.resolve())
                except ValueError as exc: raise RuntimeError("compose files must stay inside the model directory") from exc
                paths.append(path)
        for path in paths: command.extend(["-f", str(path)])
        return command

    def prepare(self):
        if not shutil.which("docker"):
            raise RuntimeError("Docker is not installed")
        try:
            compose_files = self._compose_files()
            if compose_files:
                images = []
                for path in compose_files:
                    for image in re.findall(r"(?m)^\s*image:\s*['\"]?([^\s'\"]+)", path.read_text(encoding="utf-8")):
                        image = require_docker_image(image)
                        if image not in images: images.append(image)
                if not images: raise RuntimeError("compose bundle must declare at least one pinned image")
                for image in images: subprocess.run(["docker", "pull", image], check=True)
            else:
                image = require_docker_image(self.variant.get("image", ""))
                subprocess.run(["docker", "pull", image], check=True)
        except subprocess.CalledProcessError as exc:
            raise RuntimeError("could not pull the pinned official Docker image") from exc

    def start(self):
        compose = self._compose_files()
        if compose:
            command = self._compose_command()
            subprocess.run(command + ["pull"], check=True)
            subprocess.run(command + ["up", "-d"], check=True)
            return {"container": self.name, "compose": True}
        image = require_docker_image(self.variant.get("image", ""))
        container_port = int(self.variant.get("serve", {}).get("port", self.port))
        command = ["docker", "run", "-d", "--name", self.name, "--gpus", "all",
                   "-p", f"127.0.0.1:{self.port}:{container_port}",
                   "-v", f"{self.weights}:/models/{self.slug}:ro", "--ipc", "host", image]
        serve = self.variant.get("serve", {})
        backend = serve.get("command")
        if not backend:
            raise RuntimeError("catalog variant is missing a pinned Docker serve command")
        args = backend if isinstance(backend, list) else shlex.split(backend)
        if args and str(args[0]).lower() in ("sh", "bash", "cmd", "powershell", "pwsh") and "-c" in args:
            raise RuntimeError("catalog serve commands may not invoke a shell with -c")
        for arg in args:
            arg = str(arg).replace("{port}", str(container_port)).replace("{weights}", f"/models/{self.slug}").replace("{model_dir}", f"/models/{self.slug}").replace("{slug}", self.slug)
            if "127.0.0.1" in arg: arg = arg.replace("127.0.0.1", "0.0.0.0")  # container only; host mapping stays loopback-bound
            elif arg.endswith((".py", ".sh")) and not arg.startswith("/"):
                arg = f"/models/{self.slug}/{arg}"
            command.append(arg)
        try:
            output = subprocess.run(command, check=True, text=True, capture_output=True).stdout.strip()
        except subprocess.CalledProcessError as exc:
            raise RuntimeError("could not start the model in its pinned Docker image") from exc
        return {"container": self.name, "id": output}

    def stop(self):
        if self.variant.get("serve", {}).get("compose_files"):
            subprocess.run(self._compose_command(validate=False) + ["down"], check=False, capture_output=True)
        else:
            # Selection is the exact container name created by this installation.
            subprocess.run(["docker", "rm", "-f", self.name], check=False, capture_output=True)
        return {"stopped": True, "container": self.name}

    def health(self):
        result = subprocess.run(["docker", "inspect", "--format", "{{.State.Running}}", self.name],
                                check=False, capture_output=True, text=True)
        return result.returncode == 0 and result.stdout.strip().lower() == "true" and super().health()
