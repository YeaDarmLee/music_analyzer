"""Fill docs/_migration_template.md with measured tables -> docs/COMMERCIAL_CLEAN_MIGRATION_KO.md (template is deleted afterwards)."""
import json
import numpy as np
from pathlib import Path

root = Path(__file__).resolve().parents[1]
docs = root / "docs"
read = lambda name: (docs / name).read_text(encoding="utf8", errors="replace")
core = read("COMMERCIAL_CLEAN_CORE4_SUMMARY.md").replace("��", "Δ")
pad = read("COMMERCIAL_CLEAN_PAD_SUMMARY.md")
cy = json.loads(read("COMMERCIAL_CLEAN_CYMBAL_RESULTS.json"))["rows"]
lines = ["| leak | approach | piano SDR | drums SDR | cymbal-in-piano (dB) | moved (dB) | max sum err |", "|---|---|---|---|---|---|---|"]
for leak in (None, -12, -6):
    for a in sorted({r["approach"] for r in cy}):
        s = [r for r in cy if r["approach"] == a and r["leak_db"] == leak]
        m = lambda k: np.mean([r[k] for r in s])
        lines.append(f"| {'natural' if leak is None else str(leak) + ' dB'} | {a} | {m('piano_sdr'):.2f} | {m('drums_sdr'):.2f} | {m('cymbal_in_piano_db'):.1f} | {m('moved_db'):.0f} | {max(r['sum_error'] for r in s):.1e} |")
smoke = json.loads(read("COMMERCIAL_CLEAN_SMOKE_RESULTS.json"))
rows = ["| case | state | seconds | stems | max abs partition error |", "|---|---|---|---|---|"]
for r in smoke:
    rows.append(f"| {r['case']} | {r['state']} | {r['seconds']} | {r['stems']} | {r['partition']['max_abs_error']:.2e} |" if "partition" in r
                else f"| {r['case']} | {r['state']} ({r['error']}) | {r['seconds']} | - | - |")
vc = json.loads((root / "data/commercial-eval/vocal_split/comparison.json").read_text(encoding="utf8"))
text = (docs / "_migration_template.md").read_text(encoding="utf8")
for key, value in {"CORE": core, "PAD": pad, "CYM": "\n".join(lines), "SMOKE": "\n".join(rows),
                   "BL_LEAD": f"{vc['models']['baseline']['lead_db']:.1f}", "CM_LEAD": f"{vc['models']['commercial']['lead_db']:.1f}",
                   "BL_BACK": f"{vc['models']['baseline']['backing_db']:.1f}", "CM_BACK": f"{vc['models']['commercial']['backing_db']:.1f}",
                   "AG_LEAD": f"{vc['agreement']['lead_sdr_commercial_vs_baseline']:.2f}", "AG_BACK": f"{vc['agreement']['backing_sdr_commercial_vs_baseline']:.2f}"}.items():
    text = text.replace(f"@@{key}@@", value)
assert "@@" not in text
(docs / "COMMERCIAL_CLEAN_MIGRATION_KO.md").write_text(text, encoding="utf8")
(docs / "_migration_template.md").unlink()
print(len(text))
