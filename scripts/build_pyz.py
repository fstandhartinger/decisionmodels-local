#!/usr/bin/env python3
"""Build a reproducible standard-library-only dm-local zipapp."""
import argparse
import hashlib
import io
import os
import stat
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EPOCH = (1980, 1, 1, 0, 0, 0)
SHEBANG = b"#!/usr/bin/env python3\n"


def build(output):
    files = {}
    package = ROOT / "dmlocal"
    for path in package.rglob("*.py"):
        if "__pycache__" in path.parts: continue
        files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    files["__main__.py"] = b"from dmlocal.cli import main\nraise SystemExit(main())\n"
    files["dmlocal/_catalog/models/.keep"] = b""
    catalog = ROOT / "catalog" / "models"
    if catalog.exists():
        for path in sorted(catalog.glob("*.json")):
            files["dmlocal/_catalog/models/" + path.name] = path.read_bytes()
    buffer = io.BytesIO()
    # ZIP_STORED avoids zlib-version differences across Python/OS builders.
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED, strict_timestamps=True) as archive:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, EPOCH)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            mode = stat.S_IFREG | (0o755 if name == "__main__.py" else 0o644)
            info.external_attr = mode << 16
            info.flag_bits = 0
            archive.writestr(info, files[name], compress_type=zipfile.ZIP_STORED)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(output.suffix + ".tmp")
    tmp.write_bytes(SHEBANG + buffer.getvalue())
    try: os.chmod(tmp, 0o755)
    except OSError: pass
    os.replace(tmp, output)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    return output, digest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(ROOT / "dist" / "dm-local.pyz"))
    args = parser.parse_args()
    path, digest = build(args.output)
    print(f"{path}  sha256:{digest}")


if __name__ == "__main__": main()
