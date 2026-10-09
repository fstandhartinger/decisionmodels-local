# Platform compatibility

Compatibility is declared per model variant. `dm-local plan <slug>` checks the
current machine against those declarations and the variant's memory, driver,
runtime, and recipe requirements; a platform label alone does not guarantee an
install will fit.

| Catalog platform | Intended host | Notes |
| --- | --- | --- |
| `linux-nvidia` | Linux with an NVIDIA GPU | The variant must also meet its CUDA, driver, compute-capability, and VRAM requirements. |
| `linux-cpu` | Linux CPU | Available only for variants that declare a CPU recipe. |
| `wsl2-nvidia` | NVIDIA GPU exposed through WSL2 | The selected variant must declare this platform and the Linux NVIDIA runtime requirements. |
| `macos-arm64` / `macos-arm64-metal` | Apple Silicon | Only declared author-compatible CPU, Metal, or MLX variants are considered. |
| `macos-x64` | Intel Mac | Only variants declaring this platform are considered. |
| `windows-cpu` | Windows x64 CPU | This compatibility label applies to x64 (`x86_64`/`amd64`), not Windows ARM64. |
| `windows-nvidia` | Windows x64 with NVIDIA GPU | Only explicitly declared variants are considered; vLLM and SGLang recipes use WSL2. |

The catalog can be narrower than this table for any individual model. If a
variant is not listed for the detected host, the planner reports it as
unsupported rather than estimating compatibility. For Windows GPU use, follow
the model page's runtime guidance and run `dm-local plan <slug>` inside the
environment where the model will run.
