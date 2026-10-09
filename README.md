# dm-local

`dm-local` installs a reviewed open-weights decision model on your machine or an SSH-accessible GPU node, then exposes a **Jev-compatible** local HTTP API. Weights are downloaded directly from the pinned Hugging Face revision and checked against the catalog's size and SHA-256 values; Decision Models does not rehost model weights.

## Quick start

Linux and macOS:

```sh
curl -fsSL https://github.com/fstandhartinger/decisionmodels-local/releases/latest/download/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
dm-local doctor
dm-local list
dm-local plan <model-slug>
dm-local install <model-slug>
```

Windows PowerShell 5.1 or later:

```powershell
irm https://github.com/fstandhartinger/decisionmodels-local/releases/latest/download/install.ps1 | iex
dm-local doctor
dm-local list
dm-local plan <model-slug>
dm-local install <model-slug>
```

The installer uses Python 3.9+ when available. Otherwise it downloads the pinned `uv` runtime and uses Python 3.12. The first install asks whether the software is used by an individual, an eligible small company, or a larger company. Individuals and companies with up to 10 employees and up to USD 1M ARR can use the installer free. Companies above either threshold pay USD 1,000 once plus USD 100/month, based on self-declaration. Model licences still apply separately. Non-interactive installs must pass `--usage individual|small_company|company --accept`. Company installs need an activated commercial licence.

The gateway listens on `127.0.0.1:8484` by default. Set `--listen 0.0.0.0` only when you also set `--api-key`; remote clients must send `Authorization: Bearer <key>`. Do not expose an unauthenticated gateway to a network.

## Remote machines and cloud VMs

Install through SSH using the system OpenSSH client. The command copies the running zipapp to the host, checks for Python 3.9+, bootstraps pinned `uv` if needed, runs the requested command, then opens a localhost tunnel for installs and starts:

```sh
dm-local remote -p 22 -i ~/.ssh/id_ed25519 user@gpu-host -- install <model-slug> --port 8484
```

Choose another local tunnel port with `--forward-port`, for example `--forward-port 18484`. The local endpoint uses the selected local port: `http://127.0.0.1:18484` with `--forward-port 18484`. Manage that tunnel with:

```sh
dm-local tunnel user@gpu-host status
dm-local tunnel user@gpu-host stop
```

Use this SSH transport with AWS, Azure, GCP, RunPod, Lium, CoreWeave, and self-managed nodes that expose SSH and meet the selected variant’s requirements. See [validation evidence](docs/VALIDATION.md) for the tested providers and platforms. SSH keys stay with OpenSSH; `dm-local` does not copy them.

## Commands

- `doctor [--json]` reports OS, CPU, RAM, free disk, GPUs, CUDA driver, Docker/NVIDIA runtime, Python/uv, and DMI vendor data.
- `list [--json]` shows catalog models and this machine's fit result.
- `plan <slug> [--json]` compares variants, memory needs, and available catalog guidance.
- `install <slug> [--variant ID] [--runtime docker|docker-compose|venv|llamacpp|mlx] [--port 8484] [--yes] [--no-start] [--dry-run]` verifies the licence, selects a variant, downloads weights, prepares the runtime, starts the gateway, and runs its sample decisions. `--dry-run` prints the planned downloads and commands without installing.
- `start|stop|status|logs|test <slug>` manages or checks an installation.
- `service <slug> --enable|--disable` configures a systemd user service on Linux or launchd agent on macOS.
- `licence status|declare|activate <key>` checks or manages the local usage declaration and commercial licence.
- `uninstall <slug> [--keep-weights]` removes one installation; `uninstall --all [--yes]` removes the state directory and only the exact containers recorded by `dm-local`.
- `version` prints the CLI version.

## Verify downloads and releases

Model files are fetched from `https://huggingface.co/<repo>/resolve/<revision>/<path>` (or an HTTPS `HF_ENDPOINT` mirror), resumed with HTTP Range, and verified before atomic rename. Set `HF_TOKEN` only for gated repositories. The token is sent as an authorization header and is never printed.

Release downloads include a signed `SHA256SUMS` manifest, a keyless Sigstore bundle for the zipapp, and a GitHub build-provenance attestation. Both installers verify the manifest signature against this repository's release workflow before trusting bootstrap metadata or the zipapp. If cosign is absent, they download an official verifier at a pinned SHA-256. To verify manually:

```sh
sha256sum -c SHA256SUMS
cosign verify-blob --bundle dm-local.pyz.sigstore.json \
  --certificate-identity-regexp '^https://github.com/fstandhartinger/decisionmodels-local/\.github/workflows/release\.yml@refs/tags/v[0-9][^/]*$' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com dm-local.pyz
```

Decision Models adds no usage telemetry. Setup contacts official model and source repositories, runtime and package registries, and release-signature services; commercial installations also contact the licence verification endpoint. Author runtimes remain subject to their own network behaviour.

## Troubleshooting

- **No models listed:** only catalog entries with pinned revisions, weight hashes, serving recipes, and licence evidence are shipped. Check `dm-local list` after installing a release that includes a reviewed catalog.
- **Does not fit:** use `dm-local plan <slug>` for minimum memory and supported remote-machine guidance. A variant marked quantized may be unbenchmarked; its result is not the benchmarked revision's performance.
- **Docker variant unavailable:** Linux/WSL2 NVIDIA variants need Docker, an NVIDIA driver, and the NVIDIA container runtime. Windows vLLM/SGLang use WSL2; run `wsl --install -d Ubuntu`, restart Windows, then `wsl --update` and install the current NVIDIA driver with WSL support.
- **llama.cpp unavailable:** `dm-local` only runs binaries with recorded SHA-256 pins. The current pins use official release b11260, published 29 September 2026, for Linux x64 CPU/Vulkan/CUDA 12.8, macOS arm64, and Windows x64 CPU/CUDA.
- **Download fails:** check disk space (the installer requires model size plus a 10% margin), HTTPS access to Hugging Face, the revision, and `HF_TOKEN` for gated repositories. A verified partial download can resume on the next install attempt.
- **Gateway is not healthy:** run `dm-local status <slug>` and `dm-local logs <slug>`. Local logs contain process output; request bodies and answers are not logged by the gateway.

All installer state lives under `~/.decisionmodels/` (Windows: `%LOCALAPPDATA%\DecisionModels`): models, runtimes, process records, logs, and `config.json`.
