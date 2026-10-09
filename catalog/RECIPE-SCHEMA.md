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
  "requires": {"cuda_min": "12.8", "gpu_arch_min": "sm_80", "driver_min": "570", "platforms": ["linux-nvidia"]},
  "verified": {"status": "unverified|verified", "where": "e.g. RunPod RTX 4090, 2026-10-09", "selftest": "pass"}
}
```
Placeholders: `{python}` venv interpreter, `{weights}` local weight dir, `{code:<dest>}` code dir, `{port:<name>}` ports allocated
by dm-local (names are free; `api` is the one the gateway proxies), `{state}` state dir, `{gpu}` first GPU index.
Rules: backends bind 127.0.0.1 only; no shell `-c`; commands use only files from the weights/code dirs or the venv; HF_TOKEN is never
passed to model processes; `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` are always set by dm-local for model processes.
