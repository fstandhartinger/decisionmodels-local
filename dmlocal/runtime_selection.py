"""Strict validation and hardware checks for catalog install recipes."""
import hashlib
import re
from pathlib import PurePosixPath

from .pins import require_docker_image

INSTALL_RUNTIMES = {"docker", "docker-compose", "venv", "llamacpp", "mlx"}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REVISION = re.compile(r"^[0-9a-f]{40}$")
_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_PIN = re.compile(r"^[A-Za-z0-9_.-]+==[A-Za-z0-9_.+!-]+$")
_URL_PIN = re.compile(r"^[A-Za-z0-9_.-]+\s*@\s*https://\S+#sha256=[0-9a-f]{64}$")
_LOOPBACK_READY = re.compile(r"^http://127\.0\.0\.1:(?:([0-9]{1,5})|\{port:[A-Za-z0-9_.-]+\})(?:/[^?#\r\n\\]*)?$")


def _valid_ready_url(value):
    match = _LOOPBACK_READY.fullmatch(value) if isinstance(value, str) else None
    return bool(match and (match.group(1) is None or 1 <= int(match.group(1)) <= 65535))


def _safe_relative(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value or value.startswith("~"):
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and bool(path.parts) and all(part not in ("", ".", "..") for part in path.parts)


def _is_exact_package(value):
    return isinstance(value, str) and bool(_PIN.fullmatch(value) or _URL_PIN.fullmatch(value))


def _valid_repo(value):
    if not isinstance(value, str) or not _REPO.fullmatch(value):
        return False
    return all(part not in (".", "..") for part in value.split("/"))


def recipe_errors(variant):
    """Return actionable validation errors without preventing `plan` from loading a catalog."""
    recipe = variant.get("install") if isinstance(variant, dict) else None
    if not isinstance(recipe, dict):
        return ["install recipe is missing"]
    errors = []
    runtime = recipe.get("runtime")
    if runtime not in INSTALL_RUNTIMES:
        errors.append("install.runtime must be one of docker, docker-compose, venv, llamacpp, mlx")
    if runtime in ("venv", "mlx"):
        if not isinstance(recipe.get("python"), str) or not re.fullmatch(r"\d+\.\d+", recipe.get("python", "")):
            errors.append("install.python must pin a Python major.minor version")
        packages = recipe.get("packages", [])
        if not isinstance(packages, list):
            errors.append("install.packages must be an array of exact package pins")
        elif any(not _is_exact_package(package) for package in packages):
            errors.append("install.packages must use exact == versions or HTTPS URLs with #sha256 pins")
    elif "packages" in recipe:
        packages = recipe.get("packages")
        if not isinstance(packages, list) or any(not _is_exact_package(package) for package in packages):
            errors.append("install.packages must use exact == versions or HTTPS URLs with #sha256 pins")
    if "extra_index_urls" in recipe:
        urls = recipe["extra_index_urls"]
        if not isinstance(urls, list) or any(not isinstance(url, str) or not url.startswith("https://") for url in urls):
            errors.append("install.extra_index_urls must contain HTTPS URLs")
    if "index_strategy" in recipe and recipe["index_strategy"] not in ("first-index", "unsafe-first-match", "unsafe-best-match"):
        errors.append("install.index_strategy is not a supported uv pip index strategy")

    support_files = recipe.get("support_files", [])
    if not isinstance(support_files, list):
        errors.append("install.support_files must be an array")
    else:
        support_names = set()
        for index, item in enumerate(support_files):
            label = f"install.support_files[{index}]"
            if not isinstance(item, dict):
                errors.append(f"{label} must be an object")
                continue
            path = item.get("path")
            if (not _safe_relative(path) or any(part in ("", ".", "..") for part in path.split("/"))
                    or "\x00" in path):
                errors.append(f"{label}.path must be a safe relative path")
            elif path.casefold() in support_names:
                errors.append(f"{label}.path is duplicated")
            else:
                support_names.add(path.casefold())
            content, digest = item.get("content"), item.get("sha256")
            if (not isinstance(content, str) or not isinstance(digest, str)
                    or not _SHA256.fullmatch(digest)
                    or hashlib.sha256(content.encode("utf-8")).hexdigest() != digest):
                errors.append(f"{label} needs UTF-8 content matching its SHA-256")

    venv = recipe.get("venv", {})
    if not isinstance(venv, dict):
        errors.append("install.venv must be an object")
    elif "lockfile" in venv:
        lock = venv["lockfile"]
        if not isinstance(lock, dict) or lock.get("manager") != "uv":
            errors.append("install.venv.lockfile must use manager=uv")
        else:
            if runtime not in ("venv", "mlx"):
                errors.append("install.venv.lockfile requires venv or mlx")
            path = lock.get("path")
            if not _safe_relative(path) or PurePosixPath(path).name != "uv.lock":
                errors.append("install.venv.lockfile.path must name a relative uv.lock")
            codes = recipe.get("code", [])
            if (not isinstance(lock.get("code_id"), str) or not lock["code_id"]
                    or not isinstance(codes, list)
                    or sum(isinstance(item, dict) and (item.get("id") or item.get("dest")) == lock["code_id"] for item in codes) != 1):
                errors.append("install.venv.lockfile.code_id must name one author checkout")
            if recipe.get("packages") or (isinstance(codes, list) and any(isinstance(item, dict) and item.get("pip_install") for item in codes)):
                errors.append("frozen author projects cannot use package overlays")
            extras = lock.get("extras", [])
            if not isinstance(extras, list) or any(not isinstance(extra, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", extra) for extra in extras):
                errors.append("install.venv.lockfile.extras must contain project extra names")

    image = recipe.get("image")
    if runtime in ("docker", "docker-compose"):
        if not isinstance(image, str):
            errors.append("install.image must be a digest-pinned Docker image")
        else:
            try:
                require_docker_image(image)
            except RuntimeError as exc:
                errors.append(str(exc))
    elif image is not None:
        try:
            require_docker_image(image)
        except RuntimeError as exc:
            errors.append(str(exc))

    codes = recipe.get("code", [])
    if not isinstance(codes, list):
        errors.append("install.code must be an array")
    else:
        for index, item in enumerate(codes):
            label = f"install.code[{index}]"
            if not isinstance(item, dict) or item.get("source") != "github":
                errors.append(f"{label} must use source=github")
                continue
            if not _valid_repo(item.get("repo")):
                errors.append(f"{label}.repo must be owner/name")
            if not isinstance(item.get("revision"), str) or not _REVISION.fullmatch(item.get("revision", "")):
                errors.append(f"{label}.revision must be a pinned 40-character commit")
            if not isinstance(item.get("sha256"), str) or not _SHA256.fullmatch(item.get("sha256", "")):
                errors.append(f"{label}.sha256 must be a pinned SHA-256")
            if not _safe_relative(item.get("dest")):
                errors.append(f"{label}.dest must be a safe relative path")
            if not isinstance(item.get("pip_install", False), bool) or not isinstance(item.get("deps", False), bool):
                errors.append(f"{label}.pip_install and deps must be booleans")
        if runtime not in ("venv", "mlx") and any(isinstance(item, dict) and item.get("pip_install") for item in codes):
            errors.append("install.code pip_install is supported only by venv and mlx runtimes")

    extra_weights = recipe.get("extra_weights", [])
    if not isinstance(extra_weights, list):
        errors.append("install.extra_weights must be an array")
    else:
        for index, item in enumerate(extra_weights):
            label = f"install.extra_weights[{index}]"
            if not isinstance(item, dict) or not _valid_repo(item.get("repo")):
                errors.append(f"{label}.repo must be owner/name")
                continue
            if not isinstance(item.get("revision"), str) or not _REVISION.fullmatch(item.get("revision", "")):
                errors.append(f"{label}.revision must be a pinned 40-character commit")
            if not _safe_relative(item.get("dest")):
                errors.append(f"{label}.dest must be a safe relative path")
            files = item.get("files")
            if not isinstance(files, list) or not files:
                errors.append(f"{label}.files must contain verified files")
            else:
                for file_index, file in enumerate(files):
                    if (not isinstance(file, dict) or not _safe_relative(file.get("path"))
                            or type(file.get("size")) is not int or file["size"] < 0
                            or not isinstance(file.get("sha256"), str) or not _SHA256.fullmatch(file.get("sha256", ""))):
                        errors.append(f"{label}.files[{file_index}] needs a safe path, size, and SHA-256")

    processes = recipe.get("processes", []) if runtime == "docker-compose" else recipe.get("processes")
    if not isinstance(processes, list) or (not processes and runtime != "docker-compose"):
        errors.append("install.processes must contain at least one process")
    else:
        names = set()
        for index, proc in enumerate(processes):
            label = f"install.processes[{index}]"
            if not isinstance(proc, dict):
                errors.append(f"{label} must be an object")
                continue
            name = proc.get("name")
            if not isinstance(name, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}", name):
                errors.append(f"{label}.name must be a short process name")
            elif name in names:
                errors.append(f"{label}.name is duplicated")
            else:
                names.add(name)
            command = proc.get("command")
            if not isinstance(command, list) or not command or any(not isinstance(arg, str) for arg in command):
                errors.append(f"{label}.command must be a non-empty argument array")
            elif any(arg.lower() in ("-c", "/c") or re.fullmatch(r"-[a-z]*c[a-z]*", arg.lower()) for arg in command[1:3]) and command[0].lower() in ("sh", "bash", "cmd", "powershell", "pwsh"):
                errors.append(f"{label}.command may not use a shell -c command")
            env = proc.get("env", {})
            if not isinstance(env, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in env.items()):
                errors.append(f"{label}.env must map strings to strings")
            ready = proc.get("ready")
            if not isinstance(ready, dict) or not _valid_ready_url(ready.get("url")):
                errors.append(f"{label}.ready.url must be an HTTP loopback URL")
            elif type(ready.get("timeout_s")) not in (int, float) or not 1 <= ready["timeout_s"] <= 7200:
                errors.append(f"{label}.ready.timeout_s must be between 1 and 7200 seconds")
            if runtime != "docker-compose" and isinstance(command, list) and "127.0.0.1" not in repr(command) and "127.0.0.1" not in repr(env):
                errors.append(f"{label} must explicitly bind its backend to 127.0.0.1")
            if isinstance(command, list):
                for host_key in ("--host", "--bind"):
                    if host_key in command:
                        host_index = command.index(host_key) + 1
                        if host_index >= len(command) or command[host_index] != "127.0.0.1":
                            errors.append(f"{label} must bind {host_key} to 127.0.0.1")
                if any("0.0.0.0" in arg or "::" == arg for arg in command):
                    errors.append(f"{label} may not bind to a public or wildcard address")

    api = recipe.get("api")
    if not isinstance(api, dict):
        errors.append("install.api is required")
    else:
        if api.get("mode") not in ("proxy_jev", "letter_logprobs"):
            errors.append("install.api.mode must be proxy_jev or letter_logprobs")
        if not isinstance(api.get("port"), str) or not re.fullmatch(r"[a-zA-Z0-9_.-]+", api.get("port", "")):
            errors.append("install.api.port must name a process port")
        for key in ("text_path", "image_path"):
            value = api.get(key)
            if key == "image_path" and value is None:
                continue
            if not isinstance(value, str) or not value.startswith("/") or ".." in PurePosixPath(value).parts:
                errors.append(f"install.api.{key} must be a safe absolute URL path or null for image_path")
        if api.get("model") is not None and not isinstance(api.get("model"), str):
            errors.append("install.api.model must be a string or null")
        if api.get("auth_header") is not None and (not isinstance(api.get("auth_header"), str) or "\r" in api["auth_header"] or "\n" in api["auth_header"] or ":" not in api["auth_header"]):
            errors.append("install.api.auth_header must be one complete HTTP header line or null")

        ready_ports = set()
        for proc in processes if isinstance(processes, list) else []:
            ready = proc.get("ready") if isinstance(proc, dict) else None
            ready_url = ready.get("url", "") if isinstance(ready, dict) else ""
            ready_match = re.search(r"\{port:([A-Za-z0-9_.-]+)\}", ready_url)
            if ready_match:
                ready_ports.add(ready_match.group(1))
        compose_env = (recipe.get("compose") or {}).get("env", {}) if isinstance(recipe.get("compose"), dict) else {}
        compose_ports = set()
        if isinstance(compose_env, dict):
            for value in compose_env.values():
                if isinstance(value, str):
                    compose_ports.update(re.findall(r"\{port:([A-Za-z0-9_.-]+)\}", value))
        if isinstance(api.get("port"), str) and runtime != "docker-compose" and api["port"] not in ready_ports:
            errors.append("install.api.port must name a process ready port")
        if runtime == "docker-compose" and api.get("port") not in ready_ports | compose_ports:
            errors.append("install.api.port must appear in a process ready URL or install.compose.env")

    if "requires" in recipe:
        requires = recipe["requires"]
        if not isinstance(requires, dict):
            errors.append("install.requires must be an object")
        else:
            for key in ("cuda_min", "driver_min", "gpu_arch_min", "macos_min", "glibc_min"):
                if key in requires and not isinstance(requires[key], str):
                    errors.append(f"install.requires.{key} must be a string")
            if "platforms" in requires and (not isinstance(requires["platforms"], list) or any(not isinstance(x, str) for x in requires["platforms"])):
                errors.append("install.requires.platforms must be an array of platform names")

    if runtime == "docker-compose":
        compose = recipe.get("compose")
        if not isinstance(compose, dict):
            errors.append("install.compose is required for docker-compose")
        else:
            if not _safe_relative(compose.get("bundle")):
                errors.append("install.compose.bundle must be a safe relative path in the pinned weights repo")
            if not isinstance(compose.get("bundle_sha256"), str) or not _SHA256.fullmatch(compose.get("bundle_sha256", "")):
                errors.append("install.compose.bundle_sha256 must be a SHA-256")
            if not _safe_relative(compose.get("workdir")):
                errors.append("install.compose.workdir must be a safe relative path")
            env = compose.get("env", {})
            if not isinstance(env, dict) or any(not isinstance(k, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", k) or not isinstance(v, str) or "\n" in v or "\r" in v for k, v in env.items()):
                errors.append("install.compose.env must map environment names to string values")
    return errors


def installer_runtime(variant):
    recipe = variant.get("install") or {}
    runtime = recipe.get("runtime") if isinstance(recipe, dict) else None
    return runtime if runtime in INSTALL_RUNTIMES else None


def runtime_readiness_errors(variant):
    return recipe_errors(variant)


def _version_tuple(value):
    if not isinstance(value, str):
        return None
    found = re.match(r"^\s*(\d+(?:\.\d+)*)", value)
    return tuple(int(part) for part in found.group(1).split(".")) if found else None


def _platform_names(hw):
    names = {"linux": ("linux-nvidia" if any(g.get("vendor") == "nvidia" for g in hw.get("gpus", [])) else "linux-cpu"),
             "darwin": "macos-arm64" if hw.get("arch") in ("arm64", "aarch64") else "macos-x64",
             "windows": "windows-x64"}
    result = {names.get(hw.get("os"), str(hw.get("os")))}
    if hw.get("wsl2") and "linux-nvidia" in result:
        result.add("wsl2-nvidia")
    return result


def requires_errors(variant, hw):
    """Return human-readable failures for the recipe's declared platform/driver requirements."""
    errors = []
    requires = (variant.get("install") or {}).get("requires") or {}
    platforms = requires.get("platforms") or []
    if platforms and not _platform_names(hw).intersection(platforms):
        errors.append("requires platform " + " or ".join(platforms) + "; detected " + ", ".join(sorted(_platform_names(hw))) )
    if requires.get("macos_min") and hw.get("os") == "darwin":
        actual, wanted = _version_tuple(hw.get("os_version")), _version_tuple(requires["macos_min"])
        if actual is None or wanted is None or actual < wanted:
            errors.append(f"requires macOS {requires['macos_min']} or newer; detected {hw.get('os_version') or 'unknown version'}")
    if requires.get("glibc_min") and hw.get("os") == "linux":
        libc = hw.get("libc") or {}
        actual, wanted = _version_tuple(libc.get("version")), _version_tuple(requires["glibc_min"])
        if libc.get("name") != "glibc" or actual is None or wanted is None or actual < wanted:
            errors.append(f"requires glibc {requires['glibc_min']} or newer; detected {libc.get('name') or 'unknown libc'} {libc.get('version') or ''}".strip())
    cuda_min = requires.get("cuda_min")
    if cuda_min:
        detected = hw.get("cuda_version")
        actual, wanted = _version_tuple(detected), _version_tuple(cuda_min)
        if actual is None or wanted is None or actual[:2] < wanted[:2]:
            errors.append(f"requires CUDA {cuda_min} or newer; detected {detected or 'no NVIDIA CUDA driver'}")
    driver_min = requires.get("driver_min")
    if driver_min:
        detected = hw.get("cuda_driver")
        actual, wanted = _version_tuple(detected), _version_tuple(driver_min)
        if actual is None or wanted is None or actual < wanted:
            errors.append(f"requires NVIDIA driver {driver_min} or newer; detected {detected or 'no NVIDIA driver'}")
    arch_min = requires.get("gpu_arch_min")
    if arch_min:
        match = re.fullmatch(r"sm_(\d{2,3})[a-z]?", arch_min.lower())
        caps = []
        for gpu in hw.get("gpus", []):
            try: caps.append(float(gpu.get("compute_cap")))
            except (TypeError, ValueError): pass
        required = int(match.group(1)) / 10.0 if match else None
        if required is None:
            errors.append(f"catalog minimum GPU architecture {arch_min!r} is invalid")
        elif not caps or max(caps) < required:
            errors.append(f"requires NVIDIA compute capability {required:g} or newer; detected {max(caps) if caps else 'no NVIDIA GPU'}")
    if installer_runtime(variant) in ("docker", "docker-compose"):
        docker = hw.get("docker") or {}
        if not docker.get("available"):
            errors.append("requires Docker, but Docker is unavailable")
        if not docker.get("nvidia_runtime"):
            errors.append("requires Docker with the NVIDIA container runtime")
    return errors
