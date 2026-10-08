"""Objective proxies for the blind listening checklist, commercial_6 vs basic_6, on data/listening/raw (no ground truth, no ears).

Per (song, family), values are commercial_6 minus basic_6 unless noted:
  band_db   energy difference in kick(40-120 Hz) / snare-body(150-400) / cymbal(6-16 kHz) / full band
  dip_s     seconds where the stem level falls >12 dB below its own 1 s running median while the other system's does not (and vice versa -> negative)
  hf_flux   frame-to-frame variance of 6-16 kHz magnitude (high = more 'musical noise' / sizzle)
  bleed     |corr| of the stem's 20-200 Hz envelope with the mix residual (mix - sum of all six stems of that system) is not used; instead
            'other_share_db' = other stem level relative to the mix
Output: docs/LISTENING_PROXY_RESULTS.json + a printed table.
"""
import json
from pathlib import Path
import numpy as np, soundfile as sf
from scipy.signal import stft
from scipy.ndimage import median_filter

ROOT = Path(__file__).resolve().parents[1]; RAW = ROOT / "data/listening/raw"; RATE = 44100
BANDS = {"kick": (40, 120), "body": (150, 400), "cymbal": (6000, 16000), "full": (20, 20000)}
FAMILIES = ["vocals", "piano", "guitar", "bass", "drums", "other"]
read = lambda p: sf.read(p, dtype="float32", always_2d=True)[0].mean(axis=1)

def spec(x):
    f, t, z = stft(x, RATE, nperseg=2048, noverlap=1536)
    return f, np.abs(z)

def features(x):
    f, mag = spec(x); out = {}
    for name, (lo, hi) in BANDS.items():
        sel = (f >= lo) & (f < hi); out[name] = 10 * np.log10(np.sum(mag[sel] ** 2) + 1e-12)
    hf = mag[(f >= 6000) & (f < 16000)].sum(axis=0) + 1e-9
    out["hf_flux"] = float(np.var(np.diff(np.log(hf))))
    level = 20 * np.log10(np.sqrt(np.mean(mag ** 2, axis=0)) + 1e-9)
    out["_level"] = level; out["_hop_s"] = 512 / RATE
    return out

def dip_seconds(level, hop):
    w = int(1 / hop) | 1
    base = median_filter(level, size=w, mode="nearest")
    return float(np.sum(level < base - 12) * hop)

rows = []
for song in sorted(p.name for p in RAW.iterdir() if p.is_dir()):
    mix = read(RAW / song / "clip.wav"); mix_level = 10 * np.log10(np.mean(mix.astype(np.float64) ** 2) + 1e-12)
    for fam in FAMILIES:
        feats = {}
        for preset in ("basic_6", "commercial_6"):
            x = read(RAW / song / preset / f"{fam}.wav"); feats[preset] = features(x)
            feats[preset]["share_db"] = 10 * np.log10(np.mean(x.astype(np.float64) ** 2) + 1e-12) - mix_level
        b, c = feats["basic_6"], feats["commercial_6"]
        n = min(len(b["_level"]), len(c["_level"]))
        quiet = b["share_db"] < -45 and c["share_db"] < -45
        rows.append({"song": song, "family": fam, "silent_in_both": bool(quiet),
                     **{f"{k}_db": round(c[k] - b[k], 2) for k in BANDS},
                     "share_db_basic": round(b["share_db"], 1), "share_db_commercial": round(c["share_db"], 1),
                     "dip_s_basic": round(dip_seconds(b["_level"][:n], b["_hop_s"]), 2), "dip_s_commercial": round(dip_seconds(c["_level"][:n], c["_hop_s"]), 2),
                     "hf_flux_ratio": round(c["hf_flux"] / max(b["hf_flux"], 1e-12), 2)})
(ROOT / "docs/LISTENING_PROXY_RESULTS.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
print("family    n  kick  body  cymb  full   share(b/c)   dip_s(b/c)  hf_flux_ratio(median)")
for fam in FAMILIES:
    r = [x for x in rows if x["family"] == fam and not x["silent_in_both"]]
    if not r:
        continue
    m = lambda k: np.median([x[k] for x in r])
    print(f"{fam:8} {len(r):2} {m('kick_db'):5.1f} {m('body_db'):5.1f} {m('cymbal_db'):5.1f} {m('full_db'):5.1f}  {m('share_db_basic'):6.1f}/{m('share_db_commercial'):6.1f}  {m('dip_s_basic'):4.1f}/{m('dip_s_commercial'):4.1f}  {m('hf_flux_ratio'):.2f}")
print("\nper-song drums:")
for x in rows:
    if x["family"] == "drums":
        print(x["song"], {k: x[k] for k in ("kick_db", "body_db", "cymbal_db", "full_db", "dip_s_basic", "dip_s_commercial", "hf_flux_ratio")})
