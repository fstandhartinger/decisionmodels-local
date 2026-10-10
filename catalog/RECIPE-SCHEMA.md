# Install recipe schema (catalog/1, `variants[].install`) — the runnable part of a variant

A variant is installable only when it has a valid `install` object. Prose in `serve.steps` stays as documentation only.

```jsonc
"install": {
  "runtime": "venv",                     // venv | docker | docker-compose | mlx | llamacpp
  "python": "3.12",                      // venv/mlx: uv-managed interpreter version
  "packages": ["vllm==0.30.0+cu129", "torchcodec==0.16.0+cu129"],   // exact pins only (== or direct URL + #sha256=)
  "extra_index_urls": ["https://wheels.vllm.ai/0.30.0/cu129", "https://download.pytorch.org/whl/cu129"],
  "index_strategy": "unsafe-best-match", // optional, passed to uv pip
  "code": [                              // optional: author code that is NOT in the weights repo
    {"source": "github", "repo": "aminry/decisio", "revision": "<40-hex>", "sha256": "<sha256 of codeload tarball>",
     "dest": "code/decisio", "pip_install": true}   // pip_install: `uv pip install --no-deps <dest>` (or with deps if "deps": true)
  ],
  "extra_weights": [                     // optional second HF repo (e.g. a LoRA adapter or base model for a technique)
    {"repo": "...", "revision": "<40-hex>", "dest": "weights/adapter", "files": [{"path": "...", "size": 1, "sha256": "..."}]}
  ],
  "image": "prakhar1611/xor-sglang@sha256:...",   // docker / docker-compose: third-party public image pinned by digest
  "compose": {"bundle": "serving/xor-26b-a4b-1.0-serving.tar.gz", "bundle_sha256": "...", "workdir": "xor-26b-a4b-1.0-serving",
              "env": {"MODEL_DIR": "{weights}", "API_PORT": "{port:api}", "CUDA_VISIBLE_DEVICES": "0"}},
  "processes": [                         // started in order; each must become healthy before the next starts
    {"name": "engine",
     "command": ["{python}", "-m", "vllm.entrypoints.openai.api_server", "--model", "{weights}", "--host", "127.0.0.1",
                 "--port", "{port:engine}", "--max-model-len", "40960", "--gpu-memory-utilization", "0.90"],
     "env": {"VLLM_NO_USAGE_STATS": "1", "HF_HUB_OFFLINE": "1"},
     "cwd": "{weights}",
     "ready": {"url": "http://127.0.0.1:{port:engine}/health", "timeout_s": 1200}},
    {"name": "api",
     "command": ["{python}", "{weights}/h2o_lightning_shim.py", "--port", "{port:api}"],
     "env": {"UPSTREAM": "http://127.0.0.1:{port:engine}/v1"},
     "ready": {"url": "http://127.0.0.1:{port:api}/health", "timeout_s": 120}}
  ],
  "api": {                               // how the dm-local gateway reaches the author's Jev-shaped server
    "mode": "proxy_jev",                 // proxy_jev | letter_logprobs
    "port": "api",                       // which named port
    "text_path": "/v1/systemone",        // author path for text decisions
    "image_path": "/v1/multimodal",      // author path for image decisions, or null
    "model": "h2oai/h2o-lightning-4b",   // model id the author server expects in the request body (null = leave as sent)
    "auth_header": null                  // e.g. "Authorization: Bearer local" if the author server insists on one
  },
  "requires": {"cuda_min": "12.8", "gpu_arch_min": "sm_80", "driver_min": "570", "platforms": ["linux-nvidia"], "cpu_flags": ["avx512f"], "glibc_min": "2.39"},
  "verified": {"status": "unverified|verified", "where": "e.g. RunPod RTX 4090, 2026-10-09", "selftest": "pass"}
}
```
`code[].source` is `github` (codeload archive of `repo`@`revision`) or `github-release` (the pinned release asset
`https://github.com/<repo>/releases/download/<tag>/<asset>`; fields `tag` and `asset` are plain file-name tokens, `revision` is
still the 40-hex commit and `sha256` the SHA-256 of the downloaded asset). The archive is extracted like a source archive.
`requires.cpu_flags` (list, e.g. `["avx512f"]`) makes the recipe unavailable on Linux CPUs that do not report the flag
(`hardware.cpu_flags`), for prebuilt binaries that need AVX-512. `installer_policy.status` is `supported`,
`supported_noncommercial_only`, `excluded` or `on_request` (the installer refuses it with a friendly "available on request"
message; the model page offers a request button).
Placeholders: `{python}` venv interpreter, `{weights}` local weight dir, `{code:<dest>}` code dir, `{code_<id>}` named code dir,
`{support_dir}` installer wrapper dir, `{port:<name>}` ports allocated
by dm-local (names are free; `api` is the one the gateway proxies), `{state}` state dir, `{gpu}` first GPU index.
Rules: backends bind 127.0.0.1 only; no shell `-c`; commands use only files from the weights/code/support dirs or the venv; HF_TOKEN is never
passed to model processes; `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` are always set by dm-local for model processes.


## Installer-owned support files

`install.support_files` is an optional array of objects with exactly these required fields:

```json
{"path": "server.py", "content": "print('local wrapper')\n", "sha256": "<64 lowercase hex characters>"}
```

The hash is SHA-256 of `content.encode("utf-8")`, with no newline normalization, interpolation, or added bytes.
These are our reviewed faithful wrappers, not author downloads. All entries are checked before any wrapper is
written. Unix writes traverse directories with no-follow directory handles, including the final atomic rename,
so concurrent symlink swaps cannot redirect a write outside the opened directory. Windows rechecks symlinks and
junctions before writing and before replacing; concurrent hostile directory mutation requires filesystem isolation.
Files are atomically replaced from a unique temporary file in the same directory; failed writes remove
that temporary file. Existing wrapper content is replaced only after the recipe hash is checked.

Paths are relative POSIX paths under `<state-root>/support/<model-slug>/<variant-id>/`, exposed as `{support_dir}`.
Absolute paths, `.`/`..` components, empty components, backslashes, colons, NULs, Windows device names and trailing
spaces/dots are rejected. Case-insensitive duplicate paths and existing symlinks/junctions in the destination or
its ancestors are rejected. Subdirectories are allowed. Wrapper directories can be process working directories.
Invoke Python wrappers with `["{python}", "{support_dir}/server.py", ...]`; support files are not made executable.
Docker recipes mount this directory read-only at the same absolute path. Compose bundles must declare any needed
mount themselves. Serving keeps the same token filtering, HF/Transformers offline environment and verified weights.

## Author uv lockfile projects

For `venv` and `mlx`, `install.venv.lockfile` optionally selects a frozen author project instead of a standalone
venv and pinned `uv pip install` package list:

```jsonc
"code": [{"id": "author", "source": "github", "repo": "owner/project", "revision": "<40-hex commit>",
          "sha256": "<archive SHA-256>", "dest": "code/project"}],
"venv": {"lockfile": {"code_id": "author", "path": "serving/uv.lock", "manager": "uv", "extras": ["serve"]}},
"packages": []
```

`code_id` must identify exactly one `install.code` entry by its optional `id`; an entry without `id` is identified
by its existing `dest`. `{code_<id>}` expands to the named checkout; `{code:<dest>}` continues to work. `path` is a
safe relative POSIX file path inside that checkout and must end in `uv.lock`. The adjacent `pyproject.toml` and
lockfile must exist as regular files, with no symlinks/junctions in their paths. The checkout must first be downloaded
and SHA-256 verified by the installer, with a matching source-verification marker. That existing marker is the cache
receipt; it does not rehash a locally modified extracted checkout on reuse. `manager` must be exactly `uv`.
`extras` is an optional list of project extra names (letters, digits, `_`, `-`, `.`; first character alphanumeric),
needed, for example, for an author's locked `serve` extra. No arbitrary uv arguments are accepted.

The installer acquires its existing pinned uv binary and runs:

```text
uv sync --frozen --project <directory-containing-uv.lock> --python <install.python> [--extra <name> ...]
```

The project `.venv` is forced through `UV_PROJECT_ENVIRONMENT`; inherited `VIRTUAL_ENV`, `CONDA_PREFIX`,
`PYTHONHOME` and `PYTHONPATH` are removed for sync. `{python}`, process `VIRTUAL_ENV`, the first process `PATH` entry
and relative executable lookup all select that project's `.venv` (`bin/python` on Unix, `Scripts/python.exe` on Windows).
`install.python` remains the required major.minor interpreter pin. `packages` must be omitted or empty, and all
`code[].pip_install` flags must be false/absent: overlays would defeat the frozen environment. Additional model
weights continue through the existing verified download path. Dry-run renders the same frozen sync and process
interpreter commands without acquiring uv, downloading code, creating a venv, or writing support/port files.
