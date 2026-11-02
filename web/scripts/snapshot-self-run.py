"""Snapshot public hub serving facts. Usage: python3 web/scripts/snapshot-self-run.py /path/to/hosting

Uses the hub's reviewed loader and run_command gates; never grants installer support.
Refresh after merging model-facts/model-overrides updates in the hub repository.
"""
import hashlib
import json
from pathlib import Path
import sys

hub = Path(sys.argv[1]).resolve()
sys.dont_write_bytecode = True
sys.path.insert(0, str(hub))
from dmh.catalog import load_catalog, run_command  # noqa: E402

NATIVE_ARCHS = {
    'Qwen3_5ForConditionalGeneration', 'Qwen3_5ForCausalLM',
    'Qwen3_5MoeForConditionalGeneration', 'Qwen3_5MoeForCausalLM',
    'Gemma4ForConditionalGeneration', 'Gemma4ForCausalLM',
    'Qwen3ForCausalLM', 'Qwen2ForCausalLM', 'LlamaForCausalLM',
    'Mistral3ForConditionalGeneration', 'Phi3ForCausalLM', 'Qwen3VLForConditionalGeneration',
}
models = {}
facts = json.loads((hub / 'data/model-facts.json').read_text())['models']
for slug, model in load_catalog(str(hub / 'data'))['models'].items():
    fact = facts.get(slug, {})
    command = run_command(model)
    architectures = fact.get('architectures') or []
    native = bool(architectures) and all(arch in NATIVE_ARCHS for arch in architectures)
    # A copy-ready command must be pinned, even where the hub accepts an unpinned command.
    revision = model.revision or fact.get('sha')
    if command and (not revision or fact.get('exists') is not True
                    or fact.get('format') not in ('safetensors', 'bin')
                    or fact.get('adapter_base') or not native):
        command = None
    if command:
        if not model.revision:
            command = command.replace(f'vllm serve {model.hf_repo}', f'vllm serve {model.hf_repo} --revision {revision}', 1)
        command += ' --host 127.0.0.1 --port 8000'
    missing = None if command else (
        'These weights require Hugging Face access approval.' if model.gated else
        'This repository contains an adapter, not a standalone checkpoint.' if model.adapter_base or fact.get('format') == 'lora-adapter' else
        f"This model uses its own architecture ({', '.join(architectures) or 'unknown'}); stock vLLM cannot serve it. Follow the model card's own runtime instructions." if not native else
        f'This model needs the {model.runtime} runtime; a stock vLLM command is not available.' if model.runtime != 'vllm' else
        'A standalone full checkpoint has not been verified; follow the model card for the required files and base model.' if fact.get('format') not in ('safetensors', 'bin') else
        'A pinned checkpoint revision has not been verified yet.' if not revision else
        'A stock vLLM setup has not been cleared for these weights. Check the model card and runtime instructions.'
    )
    models[slug] = dict(name=model.name, hf_repo=model.hf_repo, revision=revision, params=model.params_label,
                        vram_gb=(model.vram_gb if fact.get('format') in ('safetensors', 'bin', 'gguf') and not (model.adapter_base or fact.get('adapter_base') or fact.get('format') == 'lora-adapter') else None), precision=model.dtype, licence=model.licence,
                        gated=model.gated, adapter_base=model.adapter_base or fact.get('adapter_base'), runtime=model.runtime,
                        architectures=architectures, command=command, missing=missing)
sources = {name: hashlib.sha256((hub / 'data' / name).read_bytes()).hexdigest()
           for name in ('model-map.json', 'model-overrides.json', 'model-facts.json')}
target = Path(__file__).resolve().parents[2] / 'catalog/self-run-models.json'
target.write_text(json.dumps(dict(source='fstandhartinger/decisionmodels-hosting', sha256=sources, models=models), indent=2) + '\n')
print(f'{len(models)} models; {sum(bool(m["command"]) for m in models.values())} pinned commands -> {target}')
