"""User-local state paths. No state is written beside the executable."""
import os
import sys
from pathlib import Path


def state_dir():
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        if not base:
            base = str(Path.home() / "AppData" / "Local")
        return Path(base) / "DecisionModels"
    return Path.home() / ".decisionmodels"


def ensure_state():
    root = state_dir()
    for name in ("models", "runtimes", "run", "bin"):
        (root / name).mkdir(parents=True, exist_ok=True)
    return root


def package_catalog_dir():
    # Works for source checkout and the deterministic zipapp.
    return Path(__file__).resolve().parent.parent / "catalog" / "models"


def current_executable():
    return Path(sys.argv[0]).resolve()
