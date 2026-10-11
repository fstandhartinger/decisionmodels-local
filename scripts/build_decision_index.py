#!/usr/bin/env python3
"""Write catalog/decision-index.json: the Decision Index result for each catalogue model.

Usage: build_decision_index.py <decision-index-index.json>
Input: https://multimodalart-jev-decision-index.static.hf.space/data/index.json (the same source
decisionmodels.io/benchmarks cites). Headline metric: balanced_skill ("Full score"); rank is the
published sequential display rank including the Jev reference (v03.rank_v).
A catalogue model is matched to a Decision Index entry only when the weights repository is the same
(entry meta.model_url / weights_repo) or the JevBench key equals the entry engine key. No fuzzy names.
"""
import hashlib, json, sys
from pathlib import Path

raw_path = Path(sys.argv[1])
raw = raw_path.read_bytes()
data = json.loads(raw)
catalog = Path(__file__).resolve().parent.parent / "catalog"

by_repo = {}
for m in data["models"]:
    meta = m.get("meta") or {}
    for url in (meta.get("model_url"), meta.get("weights_repo")):
        if not url: continue
        repo = url.replace("https://huggingface.co/", "").strip("/").lower()
        by_repo.setdefault(repo, m)
by_engine = {m["engine"]: m for m in data["models"]}

models = {}
for f in sorted((catalog / "models").glob("*.json")):
    c = json.loads(f.read_text())
    key = ((c.get("benchmarks") or {}).get("jevbench") or {}).get("key")
    repo = ((c.get("weights") or {}).get("repo") or "").lower()
    entry, how = by_repo.get(repo), "weights repository"
    if entry is None and key in by_engine: entry, how = by_engine[key], "JevBench key = engine key"
    if entry is None: continue
    v = entry["v03"]
    models[c["slug"]] = {"engine": entry["engine"], "name": entry["name"], "rank": v["rank_v"], "score": v["v"], "matched_by": how}

out = {
    "schema": "decisionmodels-local-decision-index/1",
    "version": data["suite"]["label"].replace("Decision Index ", ""),
    "label": data["suite"]["label"],
    "panel_id": data["suite"]["panel_id"],
    "generated_utc": data["generated_utc"],
    "metric": "balanced_skill",
    "source": "https://multimodalart-jev-decision-index.static.hf.space/index.html",
    "data_source": "https://multimodalart-jev-decision-index.static.hf.space/data/index.json",
    "data_sha256": hashlib.sha256(raw).hexdigest(),
    "entries": len(data["models"]),
    "models": models,
}
(catalog / "decision-index.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
print(f"{len(models)} catalogue models matched of {len(list((catalog / 'models').glob('*.json')))}")
