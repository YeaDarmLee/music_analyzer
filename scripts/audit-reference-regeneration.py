"""READ-ONLY. Can every evaluation-references/*.wav of the versioned case folders be rebuilt from prepared.json (+ the reference files it names)?"""
import json, collections
from pathlib import Path
import numpy as np, soundfile as sf
cases = Path(r"C:\workspace\music_analyzer\data\ground-truth\cases")
stats = collections.Counter(); bad = []
read = lambda p: sf.read(p, dtype="float32", always_2d=True)[0]
for d in sorted(cases.glob("*-v1[0-9]/*")):
    prep = d / "prepared.json"
    if not prep.is_file() or not (d / "evaluation-references").is_dir():
        continue
    p = json.loads(prep.read_text(encoding="utf-8")); refs = p["references"]
    for f in sorted((d / "evaluation-references").glob("*.wav")):
        family = f.stem
        names = ["acoustic_guitar", "guitar"] if family == "guitar_total" else ["percussion", "pitched_percussion"] if family == "percussion" else ["synth", "synth_strings"] if family == "synth" else [family]
        have = [refs[n] for n in names if n in refs]
        existing = read(f)
        if not have:
            stats["silent_family(no reference named)" if not np.any(existing) else "NONSILENT_BUT_NO_REFERENCE"] += 1
            if np.any(existing):
                bad.append((d.name, f.name))
            continue
        missing = [r["path"] for r in have if not Path(r["path"]).is_file()]
        if missing:
            stats["reference_file_missing"] += 1; bad.append((d.name, f.name, "missing"))
            continue
        total = np.zeros_like(existing)
        for r in have:
            total += read(r["path"])
        if total.shape == existing.shape and np.array_equal(total, existing):
            stats["rebuilt_bit_identical"] += 1
        else:
            stats["differs"] += 1; bad.append((d.name, f.name, "differs"))
print(dict(stats)); print("problems:", bad[:8], len(bad))
