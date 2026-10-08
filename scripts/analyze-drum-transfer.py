"""Where does the drum signal basic_6 finds end up in commercial_6 / commercial_13 on real songs?   READ-ONLY analysis of data/listening/raw.

INPUTS (never the RMS-matched data/listening/blind files; the blind files are only for listening):
  raw/<s>/clip.wav                      the 40 s excerpt
  raw/<s>/basic_6|commercial_6|commercial_13/<family>.wav   final stems
  raw/<s>/core4raw_commercial_6|core4raw_commercial_13/<family>.wav   bs_roformer_core4 stage output as written by the model
Reference = basic_6 drums (the bs_6stem_fixed model's own drums; real GT does not exist for these songs, so this is a relative measure).
For reference R and system stems S_k: joint least squares R ~ sum a_k S_k per band. share_k = a_k<R,S_k>/<R,R>; shares sum to 1 - residual.
usage: analyze-drum-transfer.py  -> docs/DRUM_TRANSFER_RESULTS.json + printed tables
"""
import json
from pathlib import Path
import numpy as np, soundfile as sf
from scipy.signal import butter, sosfiltfilt, stft

ROOT = Path(__file__).resolve().parents[1]; RAW = ROOT / "data/listening/raw"; RATE = 44100
BANDS = {"20-80": (20, 80), "80-200": (80, 200), "200-2k": (200, 2000), "2k-8k": (2000, 8000), "8k+": (8000, 20000), "full": None}
read = lambda p: sf.read(p, dtype="float32", always_2d=True)[0].astype(np.float64)
def load(folder):
    return {p.stem: read(p) for p in sorted(Path(folder).glob("*.wav"))}
def band(x, edges):
    if edges is None:
        return x
    return sosfiltfilt(butter(4, edges, btype="bandpass", fs=RATE, output="sos"), x, axis=0)
db = lambda x: 10 * np.log10(np.mean(x ** 2) + 1e-12)

def shares(ref, stems, edges=None):
    """joint-LS attribution of ref onto stems (flattened stereo)."""
    r = band(ref, edges).ravel(); names = list(stems)
    S = np.stack([band(stems[n], edges).ravel() for n in names], axis=1)
    rr = float(r @ r) + 1e-12
    a, *_ = np.linalg.lstsq(S, r, rcond=None)
    out = {n: float(a[i] * (S[:, i] @ r) / rr) for i, n in enumerate(names)}
    out["_residual"] = float(1 - sum(out.values()))
    return out

def marginal(ref, stem, edges=None):
    r = band(ref, edges).ravel(); s = band(stem, edges).ravel()
    return float((r @ s) ** 2 / ((s @ s + 1e-12) * (r @ r + 1e-12)))

def stft_corr(a, b):
    za = np.abs(stft(a.mean(axis=1), RATE, nperseg=2048)[2]).ravel(); zb = np.abs(stft(b.mean(axis=1), RATE, nperseg=2048)[2]).ravel()
    return float(np.corrcoef(za, zb)[0, 1])

def window_transfer(ref, drums, other, win=2 * RATE):
    """per 2 s window: fraction of ref energy explained by drums-only, other-only; energy-weighted overall."""
    rows = []
    for s in range(0, len(ref) - win + 1, win):
        r = ref[s:s + win]; rows.append((float((r ** 2).sum()), marginal(r, drums[s:s + win]), marginal(r, other[s:s + win])))
    e = np.array(rows); w = e[:, 0] / e[:, 0].sum()
    return {"windows": len(e), "drums_explains_<50pct": int((e[:, 1] < .5).sum()), "other_explains_>50pct": int((e[:, 2] > .5).sum()),
            "weighted_drums": float((w * e[:, 1]).sum()), "weighted_other": float((w * e[:, 2]).sum())}

def domain(mix, stems):
    mid, side = mix.mean(axis=1), (mix[:, 0] - mix[:, 1]) / 2
    hf = band(mix, (8000, 20000)); full = np.mean(mix ** 2)
    return {"mix_rms_db": round(db(mix), 1), "crest_db": round(20 * np.log10(np.abs(mix).max() / np.sqrt(full)), 1),
            "side_over_mid_db": round(10 * np.log10(np.mean(side ** 2) / np.mean(mid ** 2)), 1),
            "hf8k_share_db": round(10 * np.log10(np.mean(hf ** 2) / full), 1),
            "vocal_share_db": round(db(stems["vocals"]) - db(mix), 1), "basic_drums_share_db": round(db(stems["drums"]) - db(mix), 1)}

results = {}
for song in sorted(p.name for p in RAW.iterdir() if p.is_dir()):
    d = RAW / song; mix = read(d / "clip.wav")
    B, C6, C13 = load(d / "basic_6"), load(d / "commercial_6"), load(d / "commercial_13")
    K6, K13 = load(d / "core4raw_commercial_6"), load(d / "core4raw_commercial_13")
    ref = B["drums"]; r = {}
    r["level_db_re_mix"] = {k: round(db(v) - db(mix), 1) for k, v in {"basic_drums": B["drums"], "c6_core4_drums": K6["drums"], "c6_final_drums": C6["drums"],
                            "c13_core4_drums": K13["drums"], "c13_final_drums": C13["drums"], "basic_other": B["other"], "c6_other": C6["other"], "c13_other": C13["other"]}.items()}
    r["c6_final_drums_eq_core4_drums"] = bool(np.array_equal(C6["drums"], K6["drums"]))
    r["core4_c6_eq_core4_c13_drums"] = bool(np.array_equal(K6["drums"], K13["drums"]))
    r["partition_err"] = {k: float(np.abs(sum(v.values()) - mix).max()) for k, v in {"basic_6": B, "commercial_6": C6, "commercial_13": C13}.items()}
    r["stft_mag_corr_basic_drums_vs"] = {f"c6_{k}": round(stft_corr(ref, v), 3) for k, v in C6.items()} | {f"c13_{k}": round(stft_corr(ref, v), 3) for k, v in C13.items() if k in ("drums", "percussion", "other")}
    r["shares_full"] = {"c6": shares(ref, C6), "c13": shares(ref, C13), "c6_core4": shares(ref, K6)}
    r["shares_by_band"] = {name: {"c6": shares(ref, C6, e), "c13": shares(ref, C13, e)} for name, e in BANDS.items() if e}
    r["windows_c6"] = window_transfer(ref, C6["drums"], C6["other"])
    # what did the core4 drums head produce, relative to its own raw output, after commercial_13's post steps
    r["core4_drums_into_c13"] = shares(K13["drums"], C13)
    r["domain"] = domain(mix, B)
    results[song] = r
(ROOT / "docs/DRUM_TRANSFER_RESULTS.json").write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")

songs = list(results); pct = lambda x: f"{100 * x:5.1f}"
print("\nTABLE 1  level of drums (dB re mix)\nsong  basic  C6core4 C6final C13core4 C13final | other: basic  C6  C13 | final==core4(C6) core4(C6)==core4(C13)")
for s in songs:
    L = results[s]["level_db_re_mix"]
    print(f"{s}  {L['basic_drums']:6.1f} {L['c6_core4_drums']:7.1f} {L['c6_final_drums']:7.1f} {L['c13_core4_drums']:7.1f} {L['c13_final_drums']:7.1f} | {L['basic_other']:6.1f} {L['c6_other']:6.1f} {L['c13_other']:6.1f} | {results[s]['c6_final_drums_eq_core4_drums']} {results[s]['core4_c6_eq_core4_c13_drums']}")
print("\nTABLE 2  basic drums -> where (joint-LS share of its energy, %)   [C6 | C13]")
for s in songs:
    a, b = results[s]["shares_full"]["c6"], results[s]["shares_full"]["c13"]
    etc6 = sum(v for k, v in a.items() if k not in ("drums", "other", "_residual")); etc13 = sum(v for k, v in b.items() if k not in ("drums", "other", "percussion", "_residual"))
    print(f"{s}  C6: drums {pct(a['drums'])} other {pct(a['other'])} etc {pct(etc6)} resid {pct(a['_residual'])} | C13: drums {pct(b['drums'])} perc {pct(b.get('percussion', 0))} other {pct(b['other'])} etc {pct(etc13)} resid {pct(b['_residual'])}")
print("\nTABLE 3  by band, mean over songs: basic drums -> C6 drums / C6 other (% energy)")
for name in [k for k in BANDS if BANDS[k]]:
    d = np.mean([results[s]["shares_by_band"][name]["c6"]["drums"] for s in songs]); o = np.mean([results[s]["shares_by_band"][name]["c6"]["other"] for s in songs])
    d13 = np.mean([results[s]["shares_by_band"][name]["c13"]["drums"] for s in songs]); p13 = np.mean([results[s]["shares_by_band"][name]["c13"].get("percussion", 0) for s in songs]); o13 = np.mean([results[s]["shares_by_band"][name]["c13"]["other"] for s in songs])
    print(f"{name:7} C6 drums {pct(d)} other {pct(o)} | C13 drums {pct(d13)} perc {pct(p13)} other {pct(o13)}")
print("\nTABLE 4  2 s windows (C6): windows where drums explain <50% / other explain >50% / energy-weighted explained by drums, other")
for s in songs:
    w = results[s]["windows_c6"]; print(f"{s}  {w['windows']} win  drums<50%: {w['drums_explains_<50pct']}  other>50%: {w['other_explains_>50pct']}  weighted drums {pct(w['weighted_drums'])} other {pct(w['weighted_other'])}")
print("\nTABLE 5  core4 drums -> C13 final stems (share %, post-step routing)")
for s in songs:
    x = results[s]["core4_drums_into_c13"]; print(s, {k: round(100 * v, 1) for k, v in x.items() if abs(v) > .01})
print("\nTABLE 6  domain features vs C6 drums loss (dB re basic)")
for s in songs:
    L = results[s]["level_db_re_mix"]; print(s, results[s]["domain"], "loss_db", round(L["c6_final_drums"] - L["basic_drums"], 1))
