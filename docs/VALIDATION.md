# Installer validation

Tests use invented sample decisions; no held-out benchmark inputs are included in this repository.

| Platform | Check | Result |
| --- | --- | --- |
| CPU-only Linux | Qwen3 0.6B Q8_0 hidden fixture, verified official GGUF and llama.cpp binary; install/start/choice self-test/stop/uninstall | Passed on Sandy, 9 October 2026. Sample-choice median809ms. The fixture validates installer infrastructure; it is not one of the benchmark top models. |
| NVIDIA Linux over SSH | H2O-Lightning-4B pinned official snapshot, vLLM0.30.0+cu129 plus pinned author shim; automatic download/runtime/endpoint/self-test; localhost SSH tunnel; separate test and uninstall | Passed on rented RunPod RTX4090 24GB, 9 October2026. Sample-choice median41.8ms. Exact node deleted after verification. |
| CoreWeave GPU sandbox | Same installer functional check, bounded owned sandbox | Pending shared GPU-slot availability. No CoreWeave runtime pass claimed. |
| macOS Apple Silicon | GitHub Actions unit/build/doctor and real tiny-model smoke | CI qualification in progress; individual author CPU/MLX/MPS recipes remain unverified unless explicitly marked. |
| Windows x64 | GitHub Actions unit/build/doctor/PowerShell parser | CI qualification in progress. NVIDIA serving uses Linux under WSL2; native CPU paths require a catalogued runnable recipe. |

Benchmark Heaven measurements describe the recorded benchmark variant and machine. They do not establish the speed, correctness or compatibility of an untested portable variant. Memory requirements for unmeasured variants are estimates. The model page and installer expose recipe availability separately from benchmark measurement.

Models remain subject to their own licences. A Decision Models commercial installer licence does not grant additional rights to third-party model weights. Weights are downloaded from the official source, never rehosted here.
