"""Runtime executor for schema-backed, pinned variant install recipes."""
import hashlib
import json
import os
import re
import shutil
import socket
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path, PurePosixPath

from ..pins import require_docker_image
from ..process import read_process, start_process, stop_process
from ..storage import download_files, hf_url, sha256_file
from .llamacpp import LlamaCppRuntime

_PORT_TOKEN = re.compile(r"\{port:([A-Za-z0-9_.-]+)\}")
_SECRET_ENV = re.compile(r"(?:_API_KEY$|^OPENAI|^ANTHROPIC)", re.IGNORECASE)
_OFFLINE_ENV = {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "DO_NOT_TRACK": "1", "VLLM_NO_USAGE_STATS": "1"}


def _safe_relpath(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value or value.startswith("~"):
        raise ValueError("path must be a safe relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError("path must be a safe relative path")
    return path


def _contained_path(base, relative):
    """Reject lexical escapes and existing symlinks before using a recipe path."""
    if not isinstance(relative, str) or any(part in ("", ".", "..") for part in relative.split("/")) or "\x00" in relative:
        raise ValueError("path must be a safe relative path")
    parts = _safe_relpath(relative).parts
    if any(part.endswith((".", " ")) or re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", part) for part in parts):
        raise ValueError("path must be a safe relative path on all platforms")
    base = Path(base).absolute()
    target = base.joinpath(*parts)
    # Include base ancestors: resolving first would conceal a symlinked support root.
    for path in [*reversed(target.parents), target]:
        try:
            reparse = getattr(path.lstat(), "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        except FileNotFoundError:
            reparse = False
        if path.is_symlink() or reparse:
            raise RuntimeError("recipe path contains a symlink or junction")
    try:
        target.resolve().relative_to(base.resolve())
    except ValueError as exc:
        raise RuntimeError("recipe path escapes its directory") from exc
    return target


def _atomic_support_write(target, data):
    """Use directory handles on Unix so a concurrent link swap cannot redirect a write."""
    if os.name == "posix":
        directory = os.open(target.anchor, os.O_RDONLY | os.O_DIRECTORY)
        temp_name = ".dm-support-" + os.urandom(16).hex()
        created = False
        try:
            for part in target.parent.parts[1:]:
                try:
                    os.mkdir(part, dir_fd=directory)
                except FileExistsError:
                    pass
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                os.close(directory)
                directory = child
            descriptor = os.open(temp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 0o600, dir_fd=directory)
            created = True
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, target.name, src_dir_fd=directory, dst_dir_fd=directory)
        finally:
            if created:
                try:
                    os.unlink(temp_name, dir_fd=directory)
                except FileNotFoundError:
                    pass
            os.close(directory)
        return
    # Windows has no openat-style directory handles in the stdlib. Recheck
    # symlinks/junctions immediately before the atomic replacement.
    target.parent.mkdir(parents=True, exist_ok=True)
    _contained_path(target.parent, target.name)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".dm-support-", delete=False) as handle:
            temp = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        _contained_path(target.parent, target.name)
        os.replace(temp, target)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def _atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, path)


def _free_loopback_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _port_owned_by_install(root, slug, recipe, state, port_name):
    runtime = state.get("runtime")
    if runtime == "docker-compose":
        result = subprocess.run(["docker", "compose", "-p", "dm-local-" + slug, "ps", "-q"],
                                check=False, capture_output=True, text=True)
        return result.returncode == 0 and bool(result.stdout.strip())
    process = next((proc for proc in recipe.get("processes", [])
                    if _PORT_TOKEN.search(proc.get("ready", {}).get("url", ""))
                    and _PORT_TOKEN.search(proc.get("ready", {}).get("url", "")).group(1) == port_name), None)
    if not process:
        return False
    name = "dm-local-" + slug + "-" + process["name"]
    if runtime == "docker":
        result = subprocess.run(["docker", "inspect", "--format", "{{.State.Running}}", name],
                                check=False, capture_output=True, text=True)
        return result.returncode == 0 and result.stdout.strip().lower() == "true"
    return read_process(root, name)["running"]


def allocate_ports(root, slug, recipe, persist=True):
    """Allocate and persist named loopback ports, retaining them across restarts."""
    names = set()
    serialized = json.dumps(recipe, ensure_ascii=False)
    names.update(_PORT_TOKEN.findall(serialized))
    api = recipe.get("api") or {}
    if api.get("port"):
        names.add(api["port"])
    record = Path(root) / "run" / (slug + ".json")
    try:
        state = json.loads(record.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    ports = dict(state.get("ports") or {})
    used = set()
    for name in sorted(names):
        value = ports.get(name)
        if isinstance(value, int) and 1 <= value <= 65535 and value not in used:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    if os.name != "nt":
                        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    sock.bind(("127.0.0.1", value))
                used.add(value)
                continue
            except OSError:
                if _port_owned_by_install(root, slug, recipe, state, name):
                    used.add(value)
                    continue
        value = _free_loopback_port()
        while value in used:
            value = _free_loopback_port()
        ports[name] = value
        used.add(value)
    state.update({"slug": slug, "ports": ports})
    if persist:
        _atomic_json(record, state)
    return ports


def expand_placeholders(value, mapping):
    """Expand the recipe's explicit placeholders in one argument or environment value."""
    text = str(value)
    for key, replacement in mapping.items():
        text = text.replace("{" + key + "}", str(replacement))
    return _PORT_TOKEN.sub(lambda match: str(mapping["port:" + match.group(1)]), text)


def _safe_extract_tar(archive_path, destination, strip_common_root=False):
    """Extract only regular files and directories; never materialize links or special files."""
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()
        names = []
        for member in members:
            if "\\" in member.name:
                raise RuntimeError("archive contains a path with Windows separators")
            name = PurePosixPath(member.name)
            if name.is_absolute() or (name.parts and re.match(r"^[A-Za-z]:", name.parts[0])) or any(part in ("..", ".") for part in name.parts):
                raise RuntimeError("archive contains an unsafe absolute or parent path")
            if not (member.isdir() or member.isfile()):
                raise RuntimeError("archive contains a link or unsupported special file")
            names.append(name)
        common_root = None
        if strip_common_root and names:
            first = names[0].parts[0] if names[0].parts else None
            if first and all(name.parts and name.parts[0] == first for name in names):
                common_root = first
        for member, name in zip(members, names):
            parts = name.parts[1:] if common_root else name.parts
            if not parts:
                continue
            target = destination.joinpath(*parts)
            try:
                target.resolve().relative_to(destination)
            except ValueError as exc:
                raise RuntimeError("archive path escapes its destination") from exc
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise RuntimeError("unable to read regular file from archive")
            with source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            try:
                target.chmod(0o755 if member.mode & 0o111 else 0o644)
            except OSError:
                pass
    return destination


def model_process_env(base=None, additions=None):
    env = dict(os.environ if base is None else base)
    env = {key: value for key, value in env.items()
           if key.upper() != "HF_TOKEN" and not _SECRET_ENV.search(key)}
    env.update(additions or {})
    env = {key: value for key, value in env.items()
           if key.upper() != "HF_TOKEN" and not _SECRET_ENV.search(key)}
    env.update(_OFFLINE_ENV)
    return env


def _tail(path, count=40):
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(lines[-count:])


def _stream_new_log(path, offset):
    try:
        with Path(path).open("rb") as handle:
            handle.seek(offset)
            data = handle.read()
            return handle.tell(), data.decode("utf-8", errors="replace")
    except OSError:
        return offset, ""


class RecipeRuntime:
    def __init__(self, model, variant, root, gateway_port=8484):
        self.model = model
        self.variant = variant
        self.recipe = variant["install"]
        self.runtime_name = self.recipe["runtime"]
        self.root = Path(root)
        self.slug = model["slug"]
        self.weights = (self.root / "models" / self.slug).resolve()
        self.runtime_dir = (self.root / "runtimes" / (self.slug + "-" + variant["id"])).resolve()
        self.support_dir = self.root.resolve() / "support" / str(_safe_relpath(self.slug)) / str(_safe_relpath(variant["id"]))
        self.venv_dir = self.runtime_dir
        self.state_file = self.root / "run" / (self.slug + ".json")
        self.gateway_port = int(gateway_port)
        self.ports = {}
        self.python = None
        self.code_dirs = {}
        self.cpp = None
        self.compose_dir = None

    def _mapping(self):
        mapping = {"weights": self.weights, "support_dir": self.support_dir, "state": self.state_file.parent,
                   "python": self.python or ("python3" if self.runtime_name == "docker" else sys.executable), "gpu": "0"}
        mapping.update({"port:" + name: value for name, value in self.ports.items()})
        mapping.update({"code:" + name: path for name, path in self.code_dirs.items()})
        for spec in self.recipe.get("code", []):
            if spec.get("id") and spec["dest"] in self.code_dirs:
                mapping["code_" + spec["id"]] = self.code_dirs[spec["dest"]]
        return mapping

    @staticmethod
    def _image_secret_keys(image, clear_hf=True):
        result = subprocess.run(["docker", "image", "inspect", "--format", "{{json .Config.Env}}", image],
                                check=False, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError("could not inspect the pinned Docker image environment")
        try:
            values = json.loads(result.stdout.strip() or "[]") or []
        except ValueError as exc:
            raise RuntimeError("Docker returned invalid image environment metadata") from exc
        if not isinstance(values, list):
            raise RuntimeError("Docker returned invalid image environment metadata")
        keys = {"HF_TOKEN"} if clear_hf else set()
        for value in values:
            key = str(value).split("=", 1)[0]
            if key.upper() == "HF_TOKEN" or _SECRET_ENV.search(key):
                keys.add(key)
        return sorted(keys)

    def _download_code(self, spec):
        repo = spec["repo"]
        revision = spec["revision"]
        dest_rel = _safe_relpath(spec["dest"])
        destination = self.weights.joinpath(*dest_rel.parts)
        marker = destination / ".dm-local-source.json"
        marker_value = {"repo": repo, "revision": revision, "sha256": spec["sha256"]}
        try:
            if json.loads(marker.read_text(encoding="utf-8")) == marker_value:
                return destination
        except (OSError, ValueError):
            pass
        destination.parent.mkdir(parents=True, exist_ok=True)
        archive = self.runtime_dir / ("code-" + re.sub(r"[^A-Za-z0-9_.-]", "-", repo) + ".tar.gz")
        archive.parent.mkdir(parents=True, exist_ok=True)
        if spec.get("source") == "github-release":
            url = f"https://github.com/{repo}/releases/download/{spec['tag']}/{spec['asset']}"
        else:
            url = f"https://codeload.github.com/{repo}/tar.gz/{revision}"
        request = urllib.request.Request(url, headers={"User-Agent": "dm-local"})
        with urllib.request.urlopen(request, timeout=90) as response, archive.open("wb") as output:
            shutil.copyfileobj(response, output)
        if sha256_file(archive) != spec["sha256"]:
            archive.unlink(missing_ok=True)
            raise RuntimeError(f"GitHub source archive for {repo} failed SHA-256 verification")
        stage = destination.with_name(destination.name + ".extracting")
        if stage.exists():
            shutil.rmtree(stage)
        _safe_extract_tar(archive, stage, strip_common_root=True)
        archive.unlink(missing_ok=True)
        if destination.exists():
            shutil.rmtree(destination)
        os.replace(stage, destination)
        marker.write_text(json.dumps(marker_value, sort_keys=True) + "\n", encoding="utf-8")
        return destination

    def _download_compose_bundle(self):
        spec = self.recipe["compose"]
        destination = self.runtime_dir / "compose-bundle"
        existing = destination.joinpath(*_safe_relpath(spec["workdir"]).parts).resolve()
        try:
            marker = json.loads((destination / ".dm-local-bundle.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            marker = None
        if existing.is_dir() and marker == {"bundle": spec["bundle"], "sha256": spec["bundle_sha256"], "revision": self.model["weights"]["revision"]}:
            self.compose_dir = existing
            return existing
        bundle_path = _safe_relpath(spec["bundle"])
        archive = self.runtime_dir / "compose-bundle.tar.gz"
        archive.parent.mkdir(parents=True, exist_ok=True)
        url = hf_url(self.model["weights"]["repo"], self.model["weights"]["revision"], str(bundle_path))
        request = urllib.request.Request(url, headers={"User-Agent": "dm-local"})
        with urllib.request.urlopen(request, timeout=90) as response, archive.open("wb") as output:
            shutil.copyfileobj(response, output)
        if sha256_file(archive) != spec["bundle_sha256"]:
            archive.unlink(missing_ok=True)
            raise RuntimeError("Docker Compose bundle failed SHA-256 verification")
        if destination.exists():
            shutil.rmtree(destination)
        _safe_extract_tar(archive, destination)
        archive.unlink(missing_ok=True)
        workdir = destination.joinpath(*_safe_relpath(spec["workdir"]).parts).resolve()
        try:
            workdir.relative_to(destination.resolve())
        except ValueError as exc:
            raise RuntimeError("Docker Compose workdir escapes the verified bundle") from exc
        if not workdir.is_dir():
            raise RuntimeError("Docker Compose workdir is missing from the verified bundle")
        _atomic_json(destination / ".dm-local-bundle.json", {"bundle": spec["bundle"], "sha256": spec["bundle_sha256"], "revision": self.model["weights"]["revision"]})
        self.compose_dir = workdir
        return workdir

    def _compose_image_refs(self):
        """Reject build and host-network compose projects and return pinned images."""
        files = sorted([*self.compose_dir.glob("*.yml"), *self.compose_dir.glob("*.yaml")])
        if not files:
            raise RuntimeError("verified Compose bundle has no compose YAML file")
        images = []
        for path in files:
            text = path.read_text(encoding="utf-8")
            if re.search(r"(?m)^\s*build\s*:", text):
                raise RuntimeError("Compose bundles with build steps are not supported")
            if re.search(r"(?m)^\s*network_mode\s*:\s*['\"]?host", text):
                raise RuntimeError("Compose bundles may not use host networking")
            images.extend(re.findall(r"(?m)^\s*image:\s*['\"]?([^\s'\"]+)", text))
            lines = text.splitlines()
            in_ports = False
            indent = 0
            for line in lines:
                match = re.match(r"^(\s*)ports\s*:\s*$", line)
                if match:
                    in_ports, indent = True, len(match.group(1))
                    continue
                if in_ports and line.strip() and len(line) - len(line.lstrip()) <= indent:
                    in_ports = False
                if in_ports and line.strip().startswith("-"):
                    value = line.strip()[1:].strip().strip("\"'")
                    if value and not value.startswith("127.0.0.1:"):
                        raise RuntimeError("Compose host ports must be bound explicitly to 127.0.0.1")
        if not images:
            raise RuntimeError("Compose bundle must declare at least one digest-pinned image")
        return list(dict.fromkeys(require_docker_image(image) for image in images))

    def _write_compose_env(self):
        spec = self.recipe["compose"]
        mapping = self._mapping()
        env = model_process_env({}, {key: expand_placeholders(value, mapping) for key, value in spec.get("env", {}).items()})
        if any("\n" in value or "\r" in value for value in env.values()):
            raise RuntimeError("Docker Compose environment values may not contain newlines")
        content = "".join(f"{key}={value}\n" for key, value in sorted(env.items()))
        env_path = self.compose_dir / ".env"
        env_path.write_text(content, encoding="utf-8")
        try: env_path.chmod(0o600)
        except OSError: pass
        return env_path

    def _write_support_files(self):
        files = self.recipe.get("support_files", [])
        if not isinstance(files, list):
            raise ValueError("install.support_files must be an array")
        pending = []
        seen = set()
        for spec in files:
            if not isinstance(spec, dict) or not isinstance(spec.get("content"), str):
                raise ValueError("support files require string content")
            digest = spec.get("sha256")
            data = spec["content"].encode("utf-8")
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest) or hashlib.sha256(data).hexdigest() != digest:
                raise RuntimeError("support file failed SHA-256 verification")
            target = _contained_path(self.support_dir, spec.get("path"))
            key = str(target).casefold()
            if key in seen:
                raise ValueError("duplicate support file path")
            seen.add(key)
            pending.append((spec["path"], data))
        # Validate the complete batch before writing even the first wrapper.
        for relative, data in pending:
            target = _contained_path(self.support_dir, relative)
            _atomic_support_write(target, data)

    def _lock_project(self, verified=True):
        venv = self.recipe.get("venv", {})
        if not isinstance(venv, dict):
            raise ValueError("install.venv must be an object")
        lock = venv.get("lockfile")
        if lock is None:
            return None
        if not isinstance(lock, dict) or lock.get("manager") != "uv":
            raise ValueError("install.venv.lockfile.manager must be uv")
        if self.runtime_name not in ("venv", "mlx"):
            raise ValueError("lockfile requires a venv or mlx runtime")
        code_id = lock.get("code_id")
        specs = [spec for spec in self.recipe.get("code", []) if (spec.get("id") or spec.get("dest")) == code_id]
        if not isinstance(code_id, str) or not code_id or len(specs) != 1:
            raise ValueError("lockfile.code_id must reference one install.code id (or dest)")
        extras = lock.get("extras", [])
        if not isinstance(extras, list) or any(not isinstance(extra, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", extra) for extra in extras):
            raise ValueError("lockfile.extras must be an array of project extra names")
        if self.recipe.get("packages") or any(spec.get("pip_install") for spec in self.recipe.get("code", [])):
            raise ValueError("frozen lockfile cannot be combined with packages or code.pip_install")
        spec = specs[0]
        checkout = Path(self.code_dirs[spec["dest"]])
        lock_path = _contained_path(checkout, lock.get("path"))
        if lock_path.name != "uv.lock":
            raise ValueError("uv lockfile path must name uv.lock")
        project = lock_path.parent
        _contained_path(checkout, (project.relative_to(checkout) / "pyproject.toml").as_posix())
        _contained_path(checkout, (project.relative_to(checkout) / ".venv").as_posix())
        if verified:
            expected = {"repo": spec["repo"], "revision": spec["revision"], "sha256": spec["sha256"]}
            marker = _contained_path(checkout, ".dm-local-source.json")
            try:
                actual = json.loads(marker.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise RuntimeError("lockfile requires a verified downloaded author checkout") from exc
            if actual != expected:
                raise RuntimeError("lockfile author checkout verification marker does not match recipe")
            if not lock_path.is_file() or not (project / "pyproject.toml").is_file():
                raise RuntimeError("verified author project must contain uv.lock and pyproject.toml")
        self.venv_dir = project / ".venv"
        self.python = str(self.venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))
        return project

    def _lock_command(self, uv, project):
        command = [uv, "sync", "--frozen", "--project", str(project), "--python", self.recipe["python"]]
        for extra in self.recipe["venv"]["lockfile"].get("extras", []):
            command.extend(["--extra", extra])
        return command

    def _prepare_python(self):
        from ..uv import ensure_uv
        project = self._lock_project()
        uv = ensure_uv(self.root)
        if project is not None:
            env = model_process_env()
            for key in ("VIRTUAL_ENV", "CONDA_PREFIX", "PYTHONHOME", "PYTHONPATH"):
                env.pop(key, None)
            env["UV_PROJECT_ENVIRONMENT"] = str(self.venv_dir)
            command = self._lock_command(str(uv), project)
            subprocess.run(command, check=True, env=env)
            if not Path(self.python).is_file():
                raise RuntimeError("uv sync did not create the project .venv Python")
            return
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.python = (str(self.runtime_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))
                       if self.runtime_name in ("venv", "mlx") else None)
        if not Path(self.python).exists():
            subprocess.run([str(uv), "venv", str(self.runtime_dir), "--python", self.recipe["python"]],
                           check=True, env=model_process_env())
        packages = self.recipe.get("packages", [])
        if packages:
            command = [str(uv), "pip", "install", "--python", self.python]
            for url in self.recipe.get("extra_index_urls", []):
                command.extend(["--extra-index-url", url])
            if self.recipe.get("index_strategy"):
                command.extend(["--index-strategy", self.recipe["index_strategy"]])
            command.extend(packages)
            subprocess.run(command, check=True, env=model_process_env())

    def prepare(self):
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.ports = allocate_ports(self.root, self.slug, self.recipe)
        runtime = self.runtime_name
        self._write_support_files()
        venv = self.recipe.get("venv", {})
        if not isinstance(venv, dict):
            raise ValueError("install.venv must be an object")
        locked = venv.get("lockfile") is not None
        if runtime in ("venv", "mlx") and not locked:
            self._prepare_python()
        for spec in self.recipe.get("code", []):
            destination = self._download_code(spec)
            self.code_dirs[spec["dest"]] = str(destination)
            if spec.get("pip_install") and not locked:
                command = [str(__import__("dmlocal.uv", fromlist=["ensure_uv"]).ensure_uv(self.root)),
                           "pip", "install", "--python", self.python]
                if not spec.get("deps", False):
                    command.append("--no-deps")
                command.append(str(destination))
                subprocess.run(command, check=True, env=model_process_env())
        if locked:
            self._prepare_python()
        for extra in self.recipe.get("extra_weights", []):
            destination = self.weights.joinpath(*_safe_relpath(extra["dest"]).parts)
            download_files(extra["files"], extra["repo"], extra["revision"], destination)
        if runtime == "llamacpp":
            self.cpp = LlamaCppRuntime(self.model, self.variant, self.root, self.ports.get((self.recipe.get("api") or {}).get("port"), 8741))
            self.cpp.prepare()
        if runtime == "docker":
            image = require_docker_image(self.recipe["image"])
            subprocess.run(["docker", "pull", image], check=True)
        if runtime == "docker-compose":
            self._download_compose_bundle()
            self._write_compose_env()
            for image in self._compose_image_refs():
                subprocess.run(["docker", "pull", image], check=True)
                secrets = self._image_secret_keys(image)
                if secrets:
                    raise RuntimeError("pinned Compose image defines prohibited secret environment variables: " + ", ".join(secrets))
        return self

    def _expanded_process(self, proc):
        mapping = self._mapping()
        command = [expand_placeholders(arg, mapping) for arg in proc["command"]]
        if self.cpp and command and command[0] in ("llama-server", "llama-server.exe"):
            command[0] = str(self.cpp.binary)
        env = model_process_env(os.environ, {key: expand_placeholders(value, mapping) for key, value in proc.get("env", {}).items()})
        if self.runtime_name in ("venv", "mlx") and self.python:
            # Same as activating the venv: JIT toolchains (ninja, triton) installed into it must be on PATH.
            venv_bin = str(self.venv_dir / ("Scripts" if os.name == "nt" else "bin"))
            env["PATH"] = venv_bin + os.pathsep + env.get("PATH", "")
            env["VIRTUAL_ENV"] = str(self.venv_dir)
        cwd_value = expand_placeholders(proc.get("cwd", str(self.weights)), mapping)
        cwd = Path(cwd_value).resolve()
        allowed = [self.weights.resolve(), self.runtime_dir.resolve(), self.support_dir.resolve(), *(Path(path).resolve() for path in self.code_dirs.values())]
        if not any(cwd == path or path in cwd.parents for path in allowed):
            raise RuntimeError("process cwd must stay inside weights, code, support, or the runtime directory")
        if not cwd.is_dir():
            raise RuntimeError(f"process working directory does not exist: {cwd}")
        if command and command[0].lower() in ("sh", "bash", "cmd", "powershell", "pwsh") and any(
                arg.lower() in ("-c", "/c") or re.fullmatch(r"-[a-z]*c[a-z]*", arg.lower()) for arg in command[1:3]):
            raise RuntimeError("model processes may not invoke a shell with -c")
        if command and self.runtime_name in ("venv", "mlx") and self.python:
            if command[0] in ("{python}", "python", "python3", str(self.python)):
                command[0] = self.python
            else:
                executable = Path(command[0])
                if not executable.is_absolute():
                    executable = self.venv_dir / ("Scripts" if os.name == "nt" else "bin") / command[0]
                # Venv entries (python, console scripts) may be symlinks into uv's interpreter store, so check the
                # unresolved absolute path against the venv and the resolved path against weights/code directories.
                unresolved = Path(os.path.abspath(executable))
                executable = executable.resolve()
                allowed_executables = [self.venv_dir.resolve(), self.runtime_dir.resolve(), self.support_dir.resolve(), self.weights.resolve(), *(Path(path).resolve() for path in self.code_dirs.values())]
                inside_venv = Path(os.path.abspath(self.venv_dir)) in unresolved.parents
                if not executable.is_file() or not (inside_venv or any(executable == base or base in executable.parents for base in allowed_executables)):
                    raise RuntimeError("process executable must be inside its venv, weights, or verified code directory")
                command[0] = str(executable)
        if command and self.runtime_name == "llamacpp":
            if self.cpp and Path(command[0]).name in ("llama-server", "llama-server.exe"):
                command[0] = str(self.cpp.binary)
            else:
                executable = Path(command[0]).resolve()
                allowed_executables = [self.venv_dir.resolve(), self.runtime_dir.resolve(), self.support_dir.resolve(), self.weights.resolve(), *(Path(path).resolve() for path in self.code_dirs.values())]
                if not executable.is_file() or not any(executable == base or base in executable.parents for base in allowed_executables):
                    raise RuntimeError("llama.cpp process executable must be the pinned llama-server binary")
        return command, env, cwd

    def _docker_run(self, proc, command, env, cwd):
        name = "dm-local-" + self.slug + "-" + proc["name"]
        image = require_docker_image(self.recipe["image"])
        own_port_token = _PORT_TOKEN.search(proc["ready"]["url"])
        own_port = self.ports.get(own_port_token.group(1)) if own_port_token else None
        args = ["docker", "run", "-d", "--name", name, "--gpus", "all", "--ipc", "host",
                "--network", "dm-local-" + self.slug]
        if own_port:
            args.extend(["-p", f"127.0.0.1:{own_port}:{own_port}"])
        args.extend(["-v", f"{self.weights}:{self.weights}:ro"])
        for code_dir in self.code_dirs.values():
            args.extend(["-v", f"{code_dir}:{code_dir}:ro"])
        if self.recipe.get("support_files"):
            args.extend(["-v", f"{self.support_dir}:{self.support_dir}:ro"])
        args.extend(["-w", str(cwd)])
        for key in self._image_secret_keys(image):
            args.extend(["-e", key + "="])
        allowed_env = set(proc.get("env", {})) | set(_OFFLINE_ENV)
        for key, value in sorted(env.items()):
            if key not in allowed_env:
                continue
            args.extend(["-e", f"{key}={self._container_value(value, proc)}"])
        args.append(image)
        command = self._docker_command(command, proc)
        args.extend(command)
        result = subprocess.run(args, check=True, capture_output=True, text=True, env=model_process_env())
        return {"name": name, "id": result.stdout.strip()}

    def _container_value(self, value, proc):
        expanded = str(value)
        for other in self.recipe.get("processes", []):
            match = _PORT_TOKEN.search(other.get("ready", {}).get("url", ""))
            if not match or other["name"] == proc["name"]:
                continue
            other_port = self.ports.get(match.group(1))
            if other_port:
                expanded = expanded.replace(f"127.0.0.1:{other_port}", f"dm-local-{self.slug}-{other['name']}:{other_port}")
        return expanded

    def _docker_command(self, command, proc):
        command = [self._container_value(arg, proc) for arg in command]
        for index, arg in enumerate(command):
            if arg == "127.0.0.1" and index and command[index - 1] in ("--host", "--bind"):
                command[index] = "0.0.0.0"
            elif arg.startswith("--host=127.0.0.1"):
                command[index] = arg.replace("127.0.0.1", "0.0.0.0", 1)
        return command

    def _ensure_docker_network(self):
        name = "dm-local-" + self.slug
        result = subprocess.run(["docker", "network", "inspect", name], check=False, capture_output=True, text=True)
        if result.returncode:
            subprocess.run(["docker", "network", "create", name], check=True, capture_output=True, text=True)

    @staticmethod
    def _stop_docker_container(name):
        stopped = subprocess.run(["docker", "stop", "--time", "20", name], check=False,
                                 capture_output=True, text=True)
        message = stopped.stderr + stopped.stdout
        if stopped.returncode and "No such container" not in message:
            return message.strip()
        removed = subprocess.run(["docker", "rm", name], check=False, capture_output=True, text=True)
        message = removed.stderr + removed.stdout
        if removed.returncode and "No such container" not in message:
            return message.strip()
        return None

    def _compose_start(self):
        self.ports = allocate_ports(self.root, self.slug, self.recipe)
        self._write_compose_env()
        self._compose_image_refs()
        result = subprocess.run(["docker", "compose", "-p", "dm-local-" + self.slug, "up", "-d"],
                                cwd=self.compose_dir, check=True, capture_output=True, text=True, env=model_process_env())
        return {"compose": True, "project": "dm-local-" + self.slug, "output": result.stdout.strip()}

    def _compose_has_exited_container(self):
        result = subprocess.run(["docker", "compose", "-p", "dm-local-" + self.slug,
                                 "ps", "--format", "json"], cwd=self.compose_dir,
                                check=False, capture_output=True, text=True)
        if result.returncode or not result.stdout.strip():
            return False
        raw = result.stdout.strip()
        try:
            decoded = json.loads(raw)
            containers = decoded if isinstance(decoded, list) else [decoded]
        except ValueError:
            try:
                containers = [json.loads(line) for line in raw.splitlines() if line.strip()]
            except ValueError:
                return False
        return any(str(item.get("State", item.get("state", ""))).lower().startswith(
                   ("exited", "dead", "removing", "created")) for item in containers if isinstance(item, dict))

    def _wait_compose_url(self, proc):
        import urllib.request
        url = expand_placeholders(proc["ready"]["url"], self._mapping())
        deadline = time.monotonic() + float(proc["ready"]["timeout_s"])
        while time.monotonic() < deadline:
            if self._compose_has_exited_container():
                break
            try:
                with urllib.request.urlopen(url, timeout=1) as response:
                    if response.status == 200:
                        return True
            except (OSError, urllib.error.URLError, TimeoutError):
                pass
            time.sleep(0.5)
        logs = subprocess.run(["docker", "compose", "-p", "dm-local-" + self.slug, "logs", "--tail", "40"],
                              cwd=self.compose_dir, check=False, capture_output=True, text=True)
        text = logs.stdout + logs.stderr
        if text:
            print(f"Last Docker Compose log lines for {proc['name']}:\n{text}", file=sys.stderr)
        raise RuntimeError(f"Compose process {proc['name']} did not become healthy within {proc['ready']['timeout_s']} seconds")

    def _wait_ready(self, proc, process_name, docker_name=None, started=None):
        import urllib.request
        mapping = self._mapping()
        url = expand_placeholders(proc["ready"]["url"], mapping)
        timeout = float(proc["ready"]["timeout_s"])
        deadline = time.monotonic() + timeout
        log_path = self.root / "run" / (process_name + ".log")
        offset = 0
        def running(name, kind):
            if kind == "docker":
                return subprocess.run(["docker", "inspect", "--format", "{{.State.Running}}", name],
                                      capture_output=True, text=True, check=False).stdout.strip().lower() == "true"
            return read_process(self.root, name)["running"]

        while time.monotonic() < deadline:
            for kind, name in started or []:
                if not running(name, kind):
                    previous = next((item for item in self.recipe.get("processes", [])
                                     if "dm-local-" + self.slug + "-" + item["name"] == name), proc)
                    previous_log = self.root / "run" / (name + ".log")
                    self._show_failure_log(previous, previous_log, name if kind == "docker" else None)
                    raise RuntimeError(f"process {previous['name']} exited before all processes became ready")
            if not running(docker_name or process_name, "docker" if docker_name else "process"):
                self._show_failure_log(proc, log_path, docker_name)
                raise RuntimeError(f"process {proc['name']} exited before becoming ready")
            try:
                with urllib.request.urlopen(url, timeout=1) as response:
                    if response.status == 200:
                        return True
            except (OSError, urllib.error.URLError, TimeoutError):
                pass
            if docker_name:
                tail = subprocess.run(["docker", "logs", "--tail", "10", docker_name], capture_output=True, text=True, check=False)
                new_text = tail.stdout + tail.stderr
                if new_text:
                    print(new_text, end="", file=sys.stderr)
            else:
                offset, new_text = _stream_new_log(log_path, offset)
                if new_text:
                    print(new_text, end="", file=sys.stderr)
            time.sleep(0.5)
        self._show_failure_log(proc, log_path, docker_name)
        raise RuntimeError(f"process {proc['name']} did not become healthy within {timeout:g} seconds")

    def _show_failure_log(self, proc, log_path, docker_name=None):
        if docker_name:
            result = subprocess.run(["docker", "logs", "--tail", "40", docker_name], capture_output=True, text=True, check=False)
            text = result.stdout + result.stderr
        else:
            text = _tail(log_path, 40)
        if text:
            print(f"Last log lines for {proc['name']}:\n{text}", file=sys.stderr)

    def start(self):
        self.ports = allocate_ports(self.root, self.slug, self.recipe)
        if self.runtime_name == "docker-compose":
            try:
                result = self._compose_start()
                for proc in self.recipe.get("processes", []):
                    self._wait_compose_url(proc)
                state = json.loads(self.state_file.read_text(encoding="utf-8"))
                state["processes"] = ["dm-local-" + self.slug]
                state["runtime"] = self.runtime_name
                _atomic_json(self.state_file, state)
                return result
            except Exception:
                if self.compose_dir is not None:
                    subprocess.run(["docker", "compose", "-p", "dm-local-" + self.slug, "down", "--timeout", "20"],
                                   cwd=self.compose_dir, check=False, capture_output=True)
                raise
        if self.runtime_name == "docker":
            self._ensure_docker_network()
        started = []
        try:
            for proc in self.recipe["processes"]:
                process_name = "dm-local-" + self.slug + "-" + proc["name"]
                command, env, cwd = self._expanded_process(proc)
                docker_name = None
                if self.runtime_name == "docker":
                    record = self._docker_run(proc, command, env, cwd)
                    docker_name = record["name"]
                    started.append(("docker", docker_name))
                else:
                    start_process(self.root, process_name, command, cwd=cwd, env=env)
                    started.append(("process", process_name))
                self._wait_ready(proc, process_name, docker_name, started=started)
            state = json.loads(self.state_file.read_text(encoding="utf-8"))
            state["processes"] = [name for _, name in started]
            state["runtime"] = self.runtime_name
            _atomic_json(self.state_file, state)
            return {"started": [name for _, name in started], "ports": self.ports}
        except Exception:
            for kind, name in reversed(started):
                if kind == "docker":
                    self._stop_docker_container(name)
                else:
                    stop_process(self.root, name, timeout=20)
            if self.runtime_name == "docker":
                subprocess.run(["docker", "network", "rm", "dm-local-" + self.slug], check=False, capture_output=True)
            try:
                state = json.loads(self.state_file.read_text(encoding="utf-8"))
                state["processes"] = []
                _atomic_json(self.state_file, state)
            except (OSError, ValueError):
                pass
            raise

    def stop(self):
        try:
            state = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            state = {}
        names = state.get("processes") or ["dm-local-" + self.slug + "-" + proc["name"] for proc in self.recipe.get("processes", [])]
        if self.runtime_name == "docker-compose":
            if self.compose_dir is None:
                self._download_compose_bundle()
            result = subprocess.run(["docker", "compose", "-p", "dm-local-" + self.slug, "down", "--timeout", "20"],
                                    cwd=self.compose_dir, check=False, capture_output=True, text=True)
            if result.returncode:
                raise RuntimeError("docker compose down failed: " + (result.stderr.strip() or result.stdout.strip()))
            state["processes"] = []
            _atomic_json(self.state_file, state)
            return {"stopped": True}
        errors = []
        for name in reversed(names):
            if self.runtime_name == "docker":
                error = self._stop_docker_container(name)
                if error:
                    errors.append(error)
            else:
                try:
                    stop_process(self.root, name, timeout=20)
                except RuntimeError as exc:
                    errors.append(str(exc))
        if self.runtime_name == "docker":
            result = subprocess.run(["docker", "network", "rm", "dm-local-" + self.slug],
                                    check=False, capture_output=True, text=True)
            if result.returncode and "No such network" not in (result.stderr + result.stdout):
                errors.append(result.stderr.strip() or result.stdout.strip())
        state["processes"] = []
        _atomic_json(self.state_file, state)
        if errors:
            raise RuntimeError("could not stop every model process: " + "; ".join(errors))
        return {"stopped": True}

    def health(self):
        try:
            self.ports = allocate_ports(self.root, self.slug, self.recipe)
            api_port = (self.recipe.get("api") or {}).get("port")
            api_process = next((proc for proc in self.recipe.get("processes", [])
                                if api_port and _PORT_TOKEN.search(proc.get("ready", {}).get("url", ""))
                                and _PORT_TOKEN.search(proc.get("ready", {}).get("url", "")).group(1) == api_port), None)
            import urllib.request
            url = expand_placeholders(api_process["ready"]["url"], self._mapping()) if api_process else f"http://127.0.0.1:{self.ports[api_port]}/health"
            with urllib.request.urlopen(url, timeout=2) as response:
                return response.status == 200
        except (KeyError, OSError, urllib.error.URLError):
            return False

    def all_ready(self):
        import urllib.request
        try:
            self.ports = allocate_ports(self.root, self.slug, self.recipe)
            state = json.loads(self.state_file.read_text(encoding="utf-8"))
            names = state.get("processes") or []
            if self.runtime_name == "docker-compose":
                if not names or not self.health():
                    return False
                self._download_compose_bundle()
                if self._compose_has_exited_container():
                    return False
                for proc in self.recipe.get("processes", []):
                    url = expand_placeholders(proc["ready"]["url"], self._mapping())
                    with urllib.request.urlopen(url, timeout=2) as response:
                        if response.status != 200:
                            return False
                return True
            if not names:
                return False
            for proc in self.recipe.get("processes", []):
                process_name = "dm-local-" + self.slug + "-" + proc["name"]
                if self.runtime_name == "docker":
                    docker_name = process_name
                    running = subprocess.run(["docker", "inspect", "--format", "{{.State.Running}}", docker_name],
                                             check=False, capture_output=True, text=True).stdout.strip().lower() == "true"
                else:
                    running = read_process(self.root, process_name)["running"]
                if not running:
                    return False
                url = expand_placeholders(proc["ready"]["url"], self._mapping())
                with urllib.request.urlopen(url, timeout=2) as response:
                    if response.status != 200:
                        return False
            return True
        except (KeyError, OSError, ValueError, urllib.error.URLError, json.JSONDecodeError):
            return False

    def runtime_commands(self):
        """Render the concrete subprocess commands for `install --dry-run`."""
        self.ports = allocate_ports(self.root, self.slug, self.recipe, persist=False)
        self.python = (str(self.runtime_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))
                       if self.runtime_name in ("venv", "mlx") else None)
        for item in self.recipe.get("code", []):
            self.code_dirs[item["dest"]] = str(self.weights.joinpath(*_safe_relpath(item["dest"]).parts))
        project = self._lock_project(verified=False)
        mapping = self._mapping()
        commands = []
        runtime = self.runtime_name
        if runtime in ("venv", "mlx"):
            if project is not None:
                commands.append(self._lock_command("uv", project))
            else:
                commands.append(["uv", "venv", str(self.runtime_dir), "--python", self.recipe["python"]])
            if self.recipe.get("packages"):
                pip = ["uv", "pip", "install", "--python", self.python]
                for url in self.recipe.get("extra_index_urls", []): pip.extend(["--extra-index-url", url])
                if self.recipe.get("index_strategy"): pip.extend(["--index-strategy", self.recipe["index_strategy"]])
                commands.append(pip + self.recipe["packages"])
        for item in self.recipe.get("code", []):
            if item.get("pip_install") and runtime in ("venv", "mlx"):
                pip = ["uv", "pip", "install", "--python", str(self.runtime_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))]
                if not item.get("deps", False):
                    pip.append("--no-deps")
                pip.append(str(self.weights.joinpath(*_safe_relpath(item["dest"]).parts)))
                commands.append(pip)
        if runtime in ("docker", "docker-compose"):
            commands.append(["docker", "pull", self.recipe["image"]])
        if runtime == "docker-compose":
            commands.append(["docker", "compose", "-p", "dm-local-" + self.slug, "up", "-d"])
        elif runtime == "docker":
            commands.append(["docker", "network", "inspect", "dm-local-" + self.slug])
            commands.append(["docker", "network", "create", "dm-local-" + self.slug])
            for proc in self.recipe.get("processes", []):
                command = [expand_placeholders(arg, mapping) for arg in proc["command"]]
                cwd = Path(expand_placeholders(proc.get("cwd", str(self.weights)), mapping)).resolve()
                name = "dm-local-" + self.slug + "-" + proc["name"]
                ready_port = _PORT_TOKEN.search(proc["ready"]["url"])
                docker = ["docker", "run", "-d", "--name", name, "--gpus", "all", "--ipc", "host",
                          "--network", "dm-local-" + self.slug]
                if ready_port:
                    port = self.ports[ready_port.group(1)]
                    docker.extend(["-p", f"127.0.0.1:{port}:{port}"])
                docker.extend(["-v", f"{self.weights}:{self.weights}:ro"])
                for code_dir in self.code_dirs.values():
                    docker.extend(["-v", f"{code_dir}:{code_dir}:ro"])
                if self.recipe.get("support_files"):
                    docker.extend(["-v", f"{self.support_dir}:{self.support_dir}:ro"])
                docker.extend(["-w", str(cwd)])
                allowed_env = {key: value for key, value in proc.get("env", {}).items()
                               if key.upper() != "HF_TOKEN" and not _SECRET_ENV.search(key)}
                allowed_env.update(_OFFLINE_ENV)
                for key, value in sorted(allowed_env.items()):
                    docker.extend(["-e", f"{key}={self._container_value(expand_placeholders(value, mapping), proc)}"])
                commands.append(["docker", "image", "inspect", "--format", "{{json .Config.Env}}", self.recipe["image"]])
                docker.append(self.recipe["image"])
                commands.append(docker + self._docker_command(command, proc))
        else:
            for proc in self.recipe.get("processes", []):
                command = [expand_placeholders(arg, mapping) for arg in proc["command"]]
                if runtime in ("venv", "mlx") and command and command[0] in ("{python}", "python", "python3"):
                    command[0] = self.python
                if runtime == "llamacpp" and command and Path(command[0]).name in ("llama-server", "llama-server.exe"):
                    command[0] = str(self.runtime_dir / "unpacked" / ("llama-server.exe" if os.name == "nt" else "llama-server"))
                commands.append(command)
        return commands
