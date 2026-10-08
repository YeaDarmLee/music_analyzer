"""Compare commercial_13 reports against the final_11 (v16) reports of the same synthetic cases; verify partition integrity.

Prints Markdown tables and writes docs/COMMERCIAL_CLEAN_PAD_RESULTS.json. GT-less stems are N/A (no invented numbers).
"""
import json
import numpy as np
from pathlib import Path
from music_analyzer.common import project_root, read_json, write_json
from music_analyzer.commercial_eval import read_audio, partition_stats
from music_analyzer.web_server import WebLibrary

base = project_root(); com_root = base / "data/commercial-eval/pad"; bas_root = base / "data/pad-eval/cases-v16"
STEMS = ("lead", "backing", "piano", "synth", "strings", "brass", "acoustic_guitar", "guitar", "bass", "drums", "percussion", "other", "guitar_total")
cases = sorted(p.name for p in com_root.iterdir() if (p / "report.json").exists())
rows, partition = [], []
for name in cases:
    com = read_json(com_root / name / "report.json"); bas = read_json(bas_root / name / "report.json")
    for stem in STEMS:
        c, b = com["metrics"].get(stem), bas["metrics"].get(stem)
        rows.append({"case": name, "stem": stem, "base": None if not b else b.get("raw_sdr_db"), "com": None if not c else c.get("raw_sdr_db"),
                     "base_si": None if not b else b.get("si_sdr_db"), "com_si": None if not c else c.get("si_sdr_db")})
    run = read_json(com_root / name / "run.json"); root = Path(run["root"])
    if "partition" in com:   # reports written since benchmark audio is discarded by default carry their own partition stats
        stats = dict(com["partition"], rms_error=com.get("sum_error_rms"), dc_offset=0.0)
        stats.update(case=name, seconds=com.get("processing_seconds")); partition.append(stats); continue
    rec = read_json(root / "web" / run["id"] / "record.json")
    library = WebLibrary.__new__(WebLibrary); library.root = root
    original = read_audio(library.track_path(rec, "original"))
    stems = [read_audio(library.track_path(rec, t["family"])) for t in rec["tracks"]]
    stats = partition_stats(original, stems); stats.update(case=name, seconds=rec.get("processing_seconds")); partition.append(stats)


def avg(sel, key):
    v = [r[key] for r in sel if r[key] is not None]
    return float(np.mean(v)) if v else None


f = lambda x: "N/A" if x is None else f"{x:.2f}"
print(f"cases: {len(cases)}\n\n| Stem | final_11 SDR | commercial_13 SDR | Delta | n |\n|---|---|---|---|---|")
for stem in STEMS:
    pairs = [r for r in rows if r["stem"] == stem and r["base"] is not None and r["com"] is not None]
    b, c = avg(pairs, "base"), avg(pairs, "com")
    print(f"| {stem} | {f(b)} | {f(c)} | {f(None if b is None or c is None else c-b)} | {len(pairs)} |")
print("\n| Partition (original vs sum of all stems) | value |\n|---|---|")
for key in ("max_abs_error", "rms_error", "samples_over_2e-6", "nan", "inf", "clipping_samples", "dc_offset"):
    print(f"| {key} (worst over cases) | {max(p[key] for p in partition):.3g} |")
print("processing seconds (mean):", avg([{"x": p["seconds"]} for p in partition], "x"))
write_json(base / "docs/COMMERCIAL_CLEAN_PAD_RESULTS.json", {"rows": rows, "partition": partition})
