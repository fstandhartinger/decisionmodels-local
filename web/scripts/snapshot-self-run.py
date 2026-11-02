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
from dmh.catalog import NATIVE_ARCHS, load_catalog, run_command_status  # noqa: E402

models = {}
facts = json.loads((hub / 'data/model-facts.json').read_text())['models']
for slug, model in load_catalog(str(hub / 'data'))['models'].items():
    fact = facts.get(slug, {})
    architectures = fact.get('architectures') or []
    revision = model.revision or fact.get('sha')
    # One gate for hub and snapshot: dmh.catalog.run_command_status (native architecture, pinned revision, full
    # safetensors/bin checkpoint, no adapter, verified repo). Hub-only text about the local guide is dropped here.
    command, missing = run_command_status(model)
    if command:
        command += ' --host 127.0.0.1 --port 8000'
    elif missing:
        missing = missing.replace(' Needs the author\'s own serving code; see the local guide.', " Follow the model card's own runtime instructions.")
    models[slug] = dict(name=model.name, hf_repo=model.hf_repo, revision=revision, params=model.params_label,
                        vram_gb=(model.vram_gb if fact.get('format') in ('safetensors', 'bin', 'gguf') and not (model.adapter_base or fact.get('adapter_base') or fact.get('format') == 'lora-adapter') else None), precision=model.dtype, licence=model.licence,
                        gated=model.gated, adapter_base=model.adapter_base or fact.get('adapter_base'), runtime=model.runtime,
                        architectures=architectures, command=command, missing=missing)
sources = {name: hashlib.sha256((hub / 'data' / name).read_bytes()).hexdigest()
           for name in ('model-map.json', 'model-overrides.json', 'model-facts.json')}
target = Path(__file__).resolve().parents[2] / 'catalog/self-run-models.json'
target.write_text(json.dumps(dict(source='fstandhartinger/decisionmodels-hosting', sha256=sources, models=models), indent=2) + '\n')
print(f'{len(models)} models; {sum(bool(m["command"]) for m in models.values())} pinned commands -> {target}')
