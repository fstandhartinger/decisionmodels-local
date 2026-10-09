"""Runtime adapters for local model backends."""

from .docker import DockerRuntime
from .llamacpp import LlamaCppRuntime
from .mlx import MlxRuntime
from .venv import VenvRuntime


def runtime_class(name):
    normalized = name.lower().replace("llama.cpp", "llamacpp")
    choices = {"docker": DockerRuntime, "venv": VenvRuntime, "llamacpp": LlamaCppRuntime, "mlx": MlxRuntime}
    try: return choices[normalized]
    except KeyError as exc: raise ValueError(f"unsupported runtime {name!r}") from exc
