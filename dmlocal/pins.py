"""Audited third-party binary and image pins. Refresh only from the cited sources."""
import re

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

# SHA-256 values computed from the official assets below. b11260 was published
# 2026-09-29T19:56:18Z (more than seven days before this pin was recorded on
# 2026-10-09). Source: https://github.com/ggml-org/llama.cpp/releases/tag/b11260
LLAMA_CPP_VERSION = "b11260"
LLAMA_CPP_RELEASE = "https://github.com/ggml-org/llama.cpp/releases/tag/b11260"
LLAMA_CPP_ASSETS = {
    "linux-x86_64-cpu": {
        "file": "llama-b11260-bin-ubuntu-x64.tar.gz",
        "url": "https://github.com/ggml-org/llama.cpp/releases/download/b11260/llama-b11260-bin-ubuntu-x64.tar.gz",
        "sha256": "af08c2f07e66ecd1252ca03c3e75b579df6cb80dac3965c65c56793b2ab9b0a0",
    },
    "linux-x86_64-vulkan": {
        "file": "llama-b11260-bin-ubuntu-vulkan-x64.tar.gz",
        "url": "https://github.com/ggml-org/llama.cpp/releases/download/b11260/llama-b11260-bin-ubuntu-vulkan-x64.tar.gz",
        "sha256": "5d034b06a5a78d2077f55a88e2689b2904abe0c8732551fd43e2983f84b9a66e",
    },
    "linux-x86_64-cuda": {
        "file": "llama-b11260-bin-ubuntu-cuda-12.8-x64.tar.gz",
        "url": "https://github.com/ggml-org/llama.cpp/releases/download/b11260/llama-b11260-bin-ubuntu-cuda-12.8-x64.tar.gz",
        "sha256": "1e2578d887bf4be72ae89332c43304c9eabb33fa15ccfc3c335779eb27bd3ddc",
    },
    "macos-arm64-metal": {
        "file": "llama-b11260-bin-macos-arm64.tar.gz",
        "url": "https://github.com/ggml-org/llama.cpp/releases/download/b11260/llama-b11260-bin-macos-arm64.tar.gz",
        "sha256": "64e7831a28330e367c6ec6dae3b9a17cc06a7c8e062bdf8b35b767c8c22c7dc5",
    },
    "windows-x86_64-cpu": {
        "file": "llama-b11260-bin-win-cpu-x64.zip",
        "url": "https://github.com/ggml-org/llama.cpp/releases/download/b11260/llama-b11260-bin-win-cpu-x64.zip",
        "sha256": "d55f92b3a7bf0a8b7d59f71e7fa76db896d2070726f26026e3ca46542d9d5733",
    },
    "windows-x86_64-cuda": {
        "file": "llama-b11260-bin-win-cuda-12.4-x64.zip",
        "url": "https://github.com/ggml-org/llama.cpp/releases/download/b11260/llama-b11260-bin-win-cuda-12.4-x64.zip",
        "sha256": "aef7825c8f7e36c03d1d02bf7c2b2a635028c916dfb7693707b54f53ea76a2e8",
    },
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
    if not isinstance(reference, str) or not re.fullmatch(r"[A-Za-z0-9._/:+-]+@sha256:[0-9a-f]{64}", reference):
        raise RuntimeError("Docker image must use a digest-pinned @sha256 reference.")
    return reference
