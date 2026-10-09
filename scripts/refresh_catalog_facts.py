#!/usr/bin/env python3
"""Refresh benchmark ranks/scores from the live Benchmark Heaven data and normalise VRAM tiers.

Usage: refresh_catalog_facts.py <jevbench-latest.json> <imagejev-v03.json>
Text: JevBench open-weights board, Capability rank (capability.open_board_rank).
Image: ImageJevBench open-weights systems within the frozen cost/latency caps, ordered by core Capability.
"""
import json, math, sys
from pathlib import Path

TIERS = [8, 12, 16, 24, 32, 48, 64, 80, 96, 141, 192]
root = Path(__file__).resolve().parent.parent / "catalog" / "models"
text = json.load(open(sys.argv[1]))
image = json.load(open(sys.argv[2]))

tsys = {s["key"]: s for s in text["systems"] if s["board"] == "open"}
caps = image["capability_eligibility"]
irows = []
for r in image["ranking"]:
    t = r["tracks"]["core"]
    lat = (t.get("speed") or {}).get("adjusted_p50_s"); cost = t.get("cost_per_1000")
    if r.get("api_flag") or not r.get("ranked") or lat is None or cost is None: continue
    if lat <= caps["latency_p50_s_cap"] and cost <= caps["cost_usd_per_1000_cap"]:
        irows.append((t["capability"], r["key"], t))
irows.sort(reverse=True)
irank = {key: (i + 1, cap, t) for i, (cap, key, t) in enumerate(irows)}

for f in sorted(root.glob("*.json")):
    d = json.loads(f.read_text())
    if d.get("hidden"): continue
    b = d.setdefault("benchmarks", {})
    if "jevbench" in b and b["jevbench"].get("key") in tsys:
        s = tsys[b["jevbench"]["key"]]
        b["jevbench"].update(version=text["revision"], capability_rank=s["capability"]["open_board_rank"],
                             capability=round(s["capability"]["score"], 2),
                             p50_s_raw=s["latency"]["p50_s_raw"],
                             page=f"https://benchmarkheaven.com/jev-models/{s['key']}")
    if "imagejevbench" in b and b["imagejevbench"].get("key") in irank:
        rank, cap, t = irank[b["imagejevbench"]["key"]]
        b["imagejevbench"].update(version=image["revision"], capability_rank=rank, capability=round(cap, 2),
                                  page="https://benchmarkheaven.com/image-jev-bench")
    for v in d.get("variants", []):
        m = v.get("min_vram_gb")
        if isinstance(m, (int, float)) and m > 0:
            v["recommended_vram_gb"] = next((t for t in TIERS if t >= m), math.ceil(m))
    f.write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n")
    print(f.stem, b.get("jevbench", {}).get("capability_rank"), b.get("imagejevbench", {}).get("capability_rank"))
