"""Resolve catalog backend descriptions to a supported installation method."""

INSTALL_RUNTIMES = {"docker", "venv", "llamacpp", "mlx"}


def _normalize(value):
    return str(value or "").strip().lower().replace("llama.cpp", "llamacpp")


def installer_runtime(variant):
    """Return a concrete installer runtime, or None when catalog data is insufficient."""
    explicit = variant.get("installer_runtime")
    if explicit is not None:
        normalized = _normalize(explicit)
        return normalized if normalized in INSTALL_RUNTIMES else None

    declared = _normalize(variant.get("runtime"))
    if declared in INSTALL_RUNTIMES:
        return declared
    serve = variant.get("serve") or {}
    if variant.get("image") or serve.get("compose_files"):
        return "docker"
    if variant.get("packages"):
        return "venv"
    return None


def runtime_readiness_errors(variant):
    runtime = installer_runtime(variant)
    if runtime is None:
        return ["catalog variant does not declare a supported installer runtime, pinned image, or pinned packages"]
    serve = variant.get("serve") or {}
    command = serve.get("command")
    has_command = isinstance(command, (str, list)) and bool(command)
    has_compose = bool(serve.get("compose_files"))

    errors = []
    if runtime == "docker":
        if not variant.get("image") and not has_compose:
            errors.append("Docker variant has no pinned image or compose bundle")
        if not has_command and not has_compose:
            errors.append("Docker variant has no structured serve.command")
    elif runtime == "venv":
        if not variant.get("packages"):
            errors.append("venv variant has no exact pinned packages")
        if not has_command:
            errors.append("venv variant has no structured serve.command")
    elif runtime == "mlx":
        if not (variant.get("packages") or variant.get("runtime_version")):
            errors.append("MLX variant has no pinned package version")
        if not has_command and not variant.get("packages") and not variant.get("runtime_version"):
            errors.append("MLX variant has no runnable server configuration")
    elif runtime == "llamacpp":
        if not any(str(item.get("path", "")).lower().endswith(".gguf") for item in variant.get("files", [])):
            errors.append("llama.cpp variant has no GGUF model file")
    return errors
