# Rune image installer recipe

`bf16-transformers-image` is a separate, source-derived Linux NVIDIA recipe. The original
`bf16-surogate-engine` text variant, including its tracked-process `runpy` launcher, is preserved.
Both use `surogate/rune-26b-a4b-GGUF@bd4a7cbbed66af1a95dfbac12cabf52e6e677411`:
11 BF16 safetensors shards and seven config/tokenizer files. The identical file list and hashes
use the installer's existing model-level weight directory; selecting another variant does not
create another snapshot. The image recipe has a separate venv/support directory and creates no
surogate engine conversion cache. Gated weights still require the user's own accepted HF terms.

## Native source and provenance

Read source only from the ImageJev intake `NOTES-vllm.md` Rune section and
`adapters_vllm.py` functions `_rune_messages` and `_load_gemma4_letter_model`, under
`/home/flori/jobs/imagejev-next-release-20261005/workers/harness/scratch/runner/intake/`.
No benchmark items, evalfiles, or sealed data were opened.

The image adapter uses Transformers 5.17.0, `Gemma4ForConditionalGeneration`, `AutoProcessor`,
BF16, SDPA, and a first-position option-logit readout. It imports the author's independent
protocol renderer. This is distinct from the author CUDA13 text engine's `--vision` path.
The BH image benchmark used choice questions; the installer's noul and score branches use the
same author's documented independent protocol functions, and have no image inference validation.

The full [official author commit](https://github.com/invergent-ai/surogate/commit/5887c223bc8d4ee3b8871f6185f215fc76b4f4de)
was expanded from `5887c223` using GitHub's commit API. Official raw source and the local
`VENDOR-SOURCE.json` match byte-for-byte (9 October 2026):

| Source at that commit | SHA-256 |
| --- | --- |
| [make_golden.py](https://github.com/invergent-ai/surogate/blob/5887c223bc8d4ee3b8871f6185f215fc76b4f4de/csrc/src/testing/serve/fixtures/serve/decisions_v1/make_golden.py) | `480f12329cf2c796e226f2c86c3cb62d5f09dfc293ca97ebd5a0b2ce5704578d` |
| [decisions.md](https://github.com/invergent-ai/surogate/blob/5887c223bc8d4ee3b8871f6185f215fc76b4f4de/docs/inference/decisions.md) | `ee0f04bf7f41afc8b4ac34fdae7e26ef9c49f9f7fbe3f5a600dcd1c94a82f8f6` |
| [Apache-2.0 LICENSE](https://github.com/invergent-ai/surogate/blob/5887c223bc8d4ee3b8871f6185f215fc76b4f4de/LICENSE) | `c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4` |

The exact `make_golden.py` and license bytes are inline SHA-pinned support files; the reference
script's fixture-generation `main()` is never called by our wrapper. At installation/inference
only its `render()` and `answer()` functions are imported. The wrapper is installer-owned code,
separately hashed. No author build scripts or author engine package are installed for this variant.

## Prompt and probability readout

The system prompt and QUESTION/OPTIONS branch come verbatim from author `render()`. User
content has the image first, followed by `SHARED STATE (JSON string):\n`,
`json.dumps(state, ensure_ascii=False)`, two newlines, and the rendered branch. Thinking is
false and the model template's generation prompt is retained. The wrapper checks the native
`<|turn>model\n<|channel>thought\n<channel|>` suffix, a single initial BOS, actual image tokens,
and that each answer letter is exactly one token and remains one continuation token at the
prompt boundary.

One forward pass per question uses `logits_to_keep=1`, `use_cache=False`. Only the option-letter
logits enter the distribution: FP32 selected logits become Python doubles; subtract the peak
and divide by fixed temperature **2**, then use the author's sequential double softmax and
answer arithmetic. No generation, chat parsing, top-k truncation, or probability proxy occurs.
Noul uses A=false, B=true regardless of input key order and returns P(true). Choice uses native
rescaled-from-uniform confidence; score uses native expected level index, modal-distance
confidence, and the native legend values. A request temperature cannot change this recipe.

Conservative transport limits: one image, 1–64 questions, 2–26 choice/score options. The BH
image adapter's A–Z path is preserved; extended option-code token filtering above 26 options
is deliberately outside this wrapper. The author reference's larger synthetic codebook is not
assumed to match the installed tokenizer. Every question uses its own full forward pass;
there is no C++ shared-prefix cache or 128-token engine prefill floor. Usage reports all tokens
actually processed, rather than the author's shared-cache count.

## HTTP and offline operation

The server binds `127.0.0.1` and exposes health after loading the model. `/v1/multimodal` accepts
Jev-compatible `state`, `questions`, and `images`: PNG/JPEG/WebP base64 data URLs, including the
author `{"url": "data:..."}` form when directly invoking the backend. The current gateway
accepts string data URLs only and applies its tighter 4 MiB / two-million-pixel limits.
The backend limits bodies to 48 MB, decoded images to 8 MB and 16 million pixels. It refuses
remote URLs and filesystem paths; it never fetches images. Invalid requests return 422,
oversized bodies 413, unknown paths 404, inference failures 500. Logs contain no request data.
`/v1/systemone` supports text through this same image variant; the independent original text
variant remains separately selectable.

Loading uses `local_files_only=True`, `trust_remote_code=False`, and the installer's offline
environment. There are no foreign-code executions, weight downloads, GPU jobs, or inference
calls during the source/transport validation of this change.

## Published dependencies and estimated resources

Python 3.12; exact pins are torch 2.8.0+cu128, torchvision 0.23.0+cu128, Transformers 5.17.0,
Accelerate 1.15.0, Pillow 12.3.0, and safetensors 0.8.0. The PyTorch pair uses the
[official CUDA 12.8 wheel index](https://download.pytorch.org/whl/cu128), with versions paired by
[PyTorch's official instructions](https://pytorch.org/get-started/previous-versions/).
Other versions were checked in official PyPI release metadata. Dependencies remain distinct
from the original CUDA13 engine recipe. Linux glibc 2.28 and sm_80 minimum are conservative
wheel/BF16 requirements. Driver 570.26 is the CUDA 12.8 GA native-driver requirement in
[NVIDIA's official release notes, table 3](https://docs.nvidia.com/cuda/archive/12.8.0/cuda-toolkit-release-notes/index.html).
This avoids relying on older-driver minor-version compatibility.

Minimum 64 GB VRAM, recommended 96 GB, and 68 GB host RAM are **estimates**, not measured peaks.
The 51.612 GB weights need additional space for image activations, KV, and runtime allocations;
large prompts can require more. The 51.64 GB disk figure describes staged weights/config files;
reserve extra disk for the Python environment and installer metadata. Single-card BF16 only;
CPU, Mac, multi-GPU and quantized image variants have not been qualified.

`install.verified.status=unverified`, `benchmarked=false`, `measured=null`, and expected speed
is explicitly not measured for this installer. AST, recipe checks, dependency resolution and
synthetic transport checks establish no inference parity, accuracy, peak-memory or speed claim.
Kernel rounding and HF image preprocessing may differ from the author's engine. A real pinned
GPU install/self-test and native image comparison remain outstanding.
