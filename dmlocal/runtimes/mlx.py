"""Apple Silicon MLX runtime."""
import platform
import subprocess

from .venv import VenvRuntime


class MlxRuntime(VenvRuntime):
    def prepare(self):
        if platform.system() != "Darwin" or platform.machine().lower() not in ("arm64", "aarch64"):
            raise RuntimeError("MLX runtime is supported only on Apple Silicon macOS")
        version = self.variant.get("runtime_version")
        packages = self.variant.get("packages") or (["mlx-lm==" + str(version)] if version else [])
        if not packages:
            raise RuntimeError("MLX variant has no pinned mlx-lm package version")
        extra_indexes = self.variant.get("extra_index_urls", [])
        self.python = self._install_packages(packages, self.variant.get("python_version"), extra_indexes)

    def start(self):
        command = self.variant.get("serve", {}).get("command")
        if command:
            return super().start()
        model = str(self.weights)
        args = [self.python, "-m", "mlx_lm.server", "--model", model, "--host", "127.0.0.1", "--port", str(self.port)]
        return self._process_start(self.name + "-backend", args, cwd=self.weights)
