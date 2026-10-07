"""Compare basic_6 vs commercial_6 per-stem SDR from data/commercial-eval/six -> stdout (Markdown) + docs/COMMERCIAL_CLEAN_SIX_RESULTS.json"""
import json, numpy as np
from pathlib import Path
from music_analyzer.common import project_root, write_json
base = project_root() / "data/commercial-eval/six"
load = lambda p: {f.stem: json.loads(f.read_text(encoding="utf8")) for f in sorted((base / p).glob("*.json"))}
b, c = load("basic_6"), load("commercial_6"); cases = sorted(set(b) & set(c))
print(f"cases: {len(cases)}\n\n| stem | basic_6 SDR | commercial_6 SDR | Delta | worst case delta | n |\n|---|---|---|---|---|---|")
summary = {}
for stem in ("piano", "guitar", "bass", "drums", "other"):
    pairs = [(b[k]["metrics"][stem]["raw_sdr_db"], c[k]["metrics"][stem]["raw_sdr_db"], k) for k in cases
             if not b[k]["metrics"][stem]["reference_absent"] and None not in (b[k]["metrics"][stem]["raw_sdr_db"], c[k]["metrics"][stem]["raw_sdr_db"])]
    if not pairs:
        print(f"| {stem} | N/A | N/A | N/A | N/A | 0 |"); continue
    x, y = np.array([p[0] for p in pairs]), np.array([p[1] for p in pairs]); d = y - x; w = int(d.argmin())
    summary[stem] = {"basic_6": float(x.mean()), "commercial_6": float(y.mean()), "delta": float(d.mean()), "worst": float(d[w]), "worst_case": pairs[w][2], "n": len(pairs)}
    print(f"| {stem} | {x.mean():.2f} | {y.mean():.2f} | {d.mean():+.2f} | {d[w]:+.2f} ({pairs[w][2]}) | {len(pairs)} |")
print(f"\nsum error max: basic_6 {max(v['sum_error'] for v in b.values()):.2e}, commercial_6 {max(v['sum_error'] for v in c.values()):.2e}")
print(f"seconds mean: basic_6 {np.mean([v['seconds'] for v in b.values()]):.1f}, commercial_6 {np.mean([v['seconds'] for v in c.values()]):.1f}")
write_json(project_root() / "docs/COMMERCIAL_CLEAN_SIX_RESULTS.json", {"summary": summary, "basic_6": b, "commercial_6": c})
