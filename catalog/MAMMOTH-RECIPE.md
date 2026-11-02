# Mammoth-1 candidate recipe

The recipe is **on request / unverified**. Nothing here establishes benchmark,
image, throughput or memory parity. Author source has been read and patched as
file data only; it has not been imported or executed on an agent workshop host.

Pins come from the public Mammoth model card and `setup.sh` at
[`61cec44c281c693992e3d6ebeb44dd3402dfa186`](https://huggingface.co/baselabs/mammoth-1/tree/61cec44c281c693992e3d6ebeb44dd3402dfa186).
That setup pins [OneJev `81ce62f1597c91e46767d4d02d6ac2e18534fe94`](https://github.com/OmniJev/OneJev/tree/81ce62f1597c91e46767d4d02d6ac2e18534fe94)
and applies `serve.patch`. The recipe hashes the immutable source archive, patch,
complete resulting file inventory and all 15 downloaded model/support files.
It executes neither `setup.sh` nor the author's decision-index evaluation kit.
No HF token or infrastructure account is required.

The installed wrapper creates the author's patched `qev.engine.DecisionEngine`
and passes it to the author's `qev.server.create_app`, binding only 127.0.0.1.
`readout.json` and `config.json` select the trained block-bidirectional full
attention / causal linear attention / slot-LM decision readout. This is the
engine used in the author's `engine.py`, with a conservative 16,384-token
branch and total-request limit matching the model card's trained context limit.
The generic qev CLI would choose its separate multimodal engine from this
checkpoint's `vision_config`; the wrapper deliberately uses the documented text
DecisionEngine. There is no image endpoint or image support claim.

The author's evaluation adapter additionally retries 32-bit-index overflow with
sequential branches. The HTTP wrapper uses the author's HTTP error behavior and
does not add that evaluation-only retry. Very large multi-question requests may
therefore fail; this is a limitation to test before extending support claims.

Direct serving packages are pinned from the author's constraints, with torch
2.8.0+cu128 / torchvision 0.23.0+cu128 matching its documented CUDA 12.8 image.
Transitive packages still resolve at install time, as for existing recipes.
The optional compiled `causal-conv1d` extension from the author's setup is not
installed by this candidate: its source build needs CUDA development tooling
and a separate no-build-isolation step. Transformers can use its PyTorch
convolution fallback; performance equivalence is not claimed. No custom
build/command hook is introduced. Lead must check this fallback works on the
GPU before accepting the candidate.

Hardware values are planning estimates, not measurements: 54.73 GB downloaded
files; 74.7 GB disk estimate includes 20 GB for runtime/cache (the installer adds
its normal 10% free-space margin); 70 GB VRAM minimum, 80 GB recommended and
80 GB host RAM allow for bf16 weights, float32 readout head, KV and activations.
The author's README states one CUDA GPU but supplies no measured minimum.
The recipe conservatively requires Ampere or newer and NVIDIA Linux driver
570.26+ / CUDA 12.8 (R580 is suitable). See [NVIDIA CUDA 12.8 release notes](https://docs.nvidia.com/cuda/archive/12.8.0/cuda-toolkit-release-notes/index.html#cuda-driver)
for the toolkit driver pairing. WSL2 also needs the corresponding Windows driver
(570.65+); neither platform has been verified by this candidate.

The model card metadata declares MIT; there is no standalone LICENSE file in the
pinned repository. The underlying Qwen3.5 base and OneJev runtime are Apache-2.0.
The recipe records that evidence and does not describe the weights as
noncommercial. It remains unverified until a disposable GPU install, typed
choice/noul/score selftest and stop/start/selftest all pass.
