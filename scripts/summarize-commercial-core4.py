"""Summarize docs/COMMERCIAL_CLEAN_CORE4_RESULTS.json into a Markdown table fragment (stdout)."""
import numpy as np
from collections import defaultdict
from music_analyzer.common import project_root, read_json

d = read_json(project_root() / "docs/COMMERCIAL_CLEAN_CORE4_RESULTS.json")
rows = d["rows"]


def avg(sel, key):
    v = [r[key] for r in sel if r.get(key) is not None]
    return float(np.mean(v)) if v else None


def f(x, p=2):
    return "N/A" if x is None else f"{x:.{p}f}"


print("### SDR / SI-SDR / leak by stem and level (mean over timbres; dB)\n")
print("| Stem | Level | SDR base | SDR core4 | Δ | SI-SDR base | SI-SDR core4 | Δ | Leak base | Leak core4 |")
print("|---|---|---|---|---|---|---|---|---|---|")
for target in ("piano", "guitar", "bass", "drums"):
    for ratio in (0, -6, -12, -18):
        b = [r for r in rows if r["target"] == target and r["ratio_db"] == ratio and r["model"] == "baseline_6s"]
        c = [r for r in rows if r["target"] == target and r["ratio_db"] == ratio and r["model"] == "core4"]
        sb, sc = avg(b, "sdr"), avg(c, "sdr"); ib, ic = avg(b, "si_sdr"), avg(c, "si_sdr")
        print(f"| {target} | {ratio} dB | {f(sb)} | {f(sc)} | {f(None if sb is None or sc is None else sc-sb)} | {f(ib)} | {f(ic)} | "
              f"{f(None if ib is None or ic is None else ic-ib)} | {f(avg(b,'leak_db'))} | {f(avg(c,'leak_db'))} |")
print("\n### Overall per stem (all levels)\n")
print("| Stem | SDR base | SDR core4 | Δ | energy ratio base | energy ratio core4 |")
print("|---|---|---|---|---|---|")
for target in ("piano", "guitar", "bass", "drums"):
    b = [r for r in rows if r["target"] == target and r["ratio_db"] is not None and r["model"] == "baseline_6s"]
    c = [r for r in rows if r["target"] == target and r["ratio_db"] is not None and r["model"] == "core4"]
    print(f"| {target} | {f(avg(b,'sdr'))} | {f(avg(c,'sdr'))} | {f(avg(c,'sdr')-avg(b,'sdr'))} | {f(avg(b,'energy_ratio_db'))} | {f(avg(c,'energy_ratio_db'))} |")
print("\n### Silence false positive (target absent; dB relative to mix, lower is better)\n")
print("| Stem | base | core4 |")
print("|---|---|---|")
for target in ("piano", "guitar", "bass", "drums"):
    b = [r for r in rows if r["target"] == target and r["ratio_db"] is None and r["model"] == "baseline_6s"]
    c = [r for r in rows if r["target"] == target and r["ratio_db"] is None and r["model"] == "core4"]
    print(f"| {target} | {f(avg(b,'silence_false_positive_db'),1)} | {f(avg(c,'silence_false_positive_db'),1)} |")
print("\n### Residual (mix minus four stems; dB re full scale) and finiteness\n")
for m in ("baseline_6s", "core4"):
    sel = [r for r in rows if r["model"] == m]
    print(f"- {m}: mean residual {f(avg(sel,'residual_db'),1)} dB, all finite: {all(r['finite'] for r in sel)}")
print("\n### Runtime\n")
for m, t in d["timing"].items():
    print(f"- {m}: {t['seconds']:.1f} s for {t['audio_seconds']:.0f} s audio (RTF {t['seconds']/t['audio_seconds']:.2f}), peak VRAM {t['peak_vram_mb']:.0f} MiB")
