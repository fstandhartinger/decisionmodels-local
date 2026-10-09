# Catalog entry schema (decisionmodels-local catalog/1) — one file per model: catalog/models/<slug>.json

```jsonc
{
  "schema": "decisionmodels-local-catalog/1",
  "slug": "h2o-lightning-4b",                      // D's model-map slug
  "name": "H2O-Lightning-4B v1.1", "author": "H2O.ai",
  "lists": ["jevbench-top10"],                      // and/or "imagejevbench-top10"
  "benchmarks": {"jevbench": {"version":"v1.6.1","key":"h2o-lightning-4b","capability_rank":5,"capability":75.0,
                 "p50_s_raw":0.12,"page":"https://benchmarkheaven.com/jev-models/h2o-lightning-4b"}},
  "modalities": ["text"],                           // or ["text","image"]
  "question_types": {"choice":"native","noul":"native","score":"native"},
  "weights": {"repo":"h2oai/h2o-lightning-4b","revision":"<40-hex commit = the benchmarked revision>",
              "url":"https://huggingface.co/h2oai/h2o-lightning-4b/tree/<rev>", "gated": false},
  "code":    null,                                  // or {"repo":"https://github.com/aminry/decisio","revision":"<sha>"} for techniques
  "base_model": {"repo":"Qwen/Qwen3.5-4B","licence":"apache-2.0"},
  "params": {"total_b":4.0,"active_b":4.0},
  "licence": {"spdx":"apache-2.0","commercial_use":"yes|no|conditional","redistribution":"yes|no|conditional",
              "notes":"plain English, 1-3 sentences","evidence":["<url of LICENSE/README at revision>"]},
  "jev_distillation": {"status":"none_found|stated|likely|unclear","evidence":"short verbatim quote or 'no training-data statement'","url":"..."},
  "installer_policy": {"status":"supported|supported_noncommercial_only|excluded","reason":"plain English"},
  "readout": {"type":"author_shim|author_server|letter_logprobs|other","endpoint":"jev|openai","backend_agnostic":true,
              "notes":"what the author's server calls on the backend (e.g. /v1/completions logprobs=20, prompt_logprobs, sglang token_ids_logprob)"},
  "variants": [
    {"id":"bf16-vllm","precision":"bf16","benchmarked":true,"runtime":"vllm","runtime_version":"0.30.0+cu129",
     "image": null, // or pinned docker image "repo@sha256:..." exactly as BH ran it (only third-party public images)
     "platforms":["linux-nvidia","wsl2-nvidia"],"gpu_arch_min":"sm_80",
     "min_vram_gb":12,"recommended_vram_gb":16,"min_ram_gb":16,"disk_gb":9.5,
     "files":[{"path":"model.safetensors","size":8000000000,"sha256":"<lfs oid>"}], // every file needed, from HF tree API at revision
     "serve":{"recipe_source":"/home/flori/jobs/.../h2o-lightning-4b","port":8741,
              "steps":["exact commands BH used, with flags; where author serve.sh exists, reference it by path in the repo"]},
     "measured":{"gpu":"RTX PRO 6000 96GB","p50_ms":120,"source":"BH v1.6.1 row"},
     "expected_speed":"plain English e.g. ~0.1-0.2 s per decision on RTX 4090; CPU not supported",
     "notes":""},
    {"id":"q8_0-llamacpp","precision":"gguf-q8_0","benchmarked":false,"runtime":"llama.cpp", "...":"..."}
  ],
  "sources_checked_utc":"2026-10-09T17:00Z"
}
```
Rules: no invented numbers. VRAM = weights + KV/activation headroom at the BH context setting; say how you derived it.
Non-benchmarked variants (quantised, llama.cpp, MLX) only if a credible path exists (official GGUF/MLX repo from the author, or
author readout is backend-agnostic so llama.cpp/MLX OpenAI-compatible logprobs could replace vLLM); mark `benchmarked:false`.
