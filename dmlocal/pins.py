"""Audited third-party binary and image pins. Refresh only from the cited sources."""

# uv 0.12.24, GitHub release and its sha256.sum, checked 2026-10-09.
# Source: https://github.com/astral-sh/uv/releases/tag/0.12.24
UV_VERSION = "0.12.24"
UV_RELEASE = "https://github.com/astral-sh/uv/releases/download/0.12.24"
UV_ASSETS = {
    "x86_64-unknown-linux-gnu": {
        "file": "uv-x86_64-unknown-linux-gnu.tar.gz",
        "sha256": "b4dfaef47d491a7296981f8374a4595f55dbf84e8937c8ecd2983574d8bb3da6",
    },
    "aarch64-unknown-linux-gnu": {
        "file": "uv-aarch64-unknown-linux-gnu.tar.gz",
        "sha256": "5231be65f496304623895dacdbf1de8504fec90303684bdf05805aa34414dd21",
    },
    "aarch64-apple-darwin": {
        "file": "uv-aarch64-apple-darwin.tar.gz",
        "sha256": "0c4346de7abdb49495b393b9ec809fe387aa43e586be20fecb972216c1e71732",
    },
    "x86_64-apple-darwin": {
        "file": "uv-x86_64-apple-darwin.tar.gz",
        "sha256": "4fa82e37cb94767661f532b001e470b67a186c7260e305bd84ddb78fd545c0b6",
    },
    "x86_64-pc-windows-msvc": {
        "file": "uv-x86_64-pc-windows-msvc.zip",
        "sha256": "7c38608c8a18ee137d748a1773053b07ec8f3a30fab49aebaa6f4e4efeceb019",
    },
    "aarch64-pc-windows-msvc": {
        "file": "uv-aarch64-pc-windows-msvc.zip",
        "sha256": "4b783bda5cc44bbae0651a837223873a7acee31152381aef5fc86ef6bef25997",
    },
}

# The official ggml-org release currently publishes source only, no per-platform
# llama-server assets. Refuse that runtime until an asset hash is published and
# independently recorded here. Source checked via the GitHub releases API on
# 2026-10-09: https://api.github.com/repos/ggml-org/llama.cpp/releases/latest
LLAMA_CPP_VERSION = "v0.6.0"
LLAMA_CPP_RELEASE = "https://github.com/ggml-org/llama.cpp/releases/tag/v0.6.0"
LLAMA_CPP_ASSETS = {
    "linux-x86_64-cpu": None,
    "linux-x86_64-cuda": None,
    "linux-x86_64-vulkan": None,
    "macos-arm64-metal": None,
    "windows-x86_64-cpu": None,
    "windows-x86_64-cuda": None,
}

# Docker Hub official-image manifest-list digests, checked 2026-10-09.
# Sources: https://hub.docker.com/r/vllm/vllm-openai and
# https://hub.docker.com/r/lmsysorg/sglang (Registry v2 manifests, tag latest).
DOCKER_IMAGES = {
    "vllm/vllm-openai": "sha256:c1c9f6fd5c109ba7f0546a59f5b2f15fb87f64c77782e90a27b648b42a8e67c3",
    "lmsysorg/sglang": "sha256:b1259f3ea3275f66237c498ea388919729018bc9f01c3d638391e06e2cf3f469",
}


def require_llama_asset(platform_key):
    asset = LLAMA_CPP_ASSETS.get(platform_key)
    if not asset or not asset.get("sha256"):
        raise RuntimeError(
            "The official llama.cpp release has no verified binary pin for "
            f"{platform_key}. See {LLAMA_CPP_RELEASE}; this path is disabled until a SHA-256 is recorded."
        )
    return asset


def require_docker_image(reference):
    if "@" not in reference:
        raise RuntimeError("Docker image must use a pinned @sha256 digest from the catalog.")
    name, digest = reference.rsplit("@", 1)
    expected = DOCKER_IMAGES.get(name)
    if not expected or digest != expected:
        raise RuntimeError(f"Docker image {name!r} does not match a verified official-image pin in dmlocal/pins.py.")
    return reference
