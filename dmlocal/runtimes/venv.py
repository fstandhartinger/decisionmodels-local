"""Pinned-package Python environment for catalog author serve commands."""
import os
import subprocess

from .base import Runtime


class VenvRuntime(Runtime):
    def prepare(self):
        packages = self.variant.get("packages", [])
        extra_indexes = self.variant.get("extra_index_urls", [])
        self.python = self._install_packages(packages, self.variant.get("python_version"), extra_indexes)
        if self.python is None:
            raise RuntimeError("venv variant has no pinned packages in the catalog")

    def start(self):
        args = self._serve_command()
        if args[0] in ("python", "python3"):
            args[0] = self.python
        env = os.environ.copy()
        env.pop("HF_TOKEN", None)
        env["DM_LOCAL_MODEL_DIR"] = str(self.weights)
        env["DM_LOCAL_PORT"] = str(self.port)
        return self._process_start(self.name + "-backend", args, cwd=self.weights, env=env)

    def stop(self):
        return self._process_stop(self.name + "-backend")
