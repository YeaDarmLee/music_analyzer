"""Phase C: mixture-consistent Wiener refinement of core4 RAW stems (no new weights). Evidence only; production untouched.

Norbert 0.2.1 (MIT, Inria; wheel sha256 409ac3f1...b74339) is imported from an isolated folder (data/tmp-norbert/site), NOT installed into the project venv.
Sources = core4 piano/guitar/bass/drums magnitude STFTs (+ residual = mix - sum as a 5th source for the '5src' variants).
A raw | B ratio mask (softmask) | C wiener 1 iter | D wiener 2 iter  (5 sources incl. residual)   | C4 wiener 1 iter with 4 sources only (other = mix - sum)
The last source is always re-derived as mix - sum(others) in the time domain, so partition error stays at float precision.
Output: docs/COMMERCIAL_CLEAN_WIENER_RESULTS.json
"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data/tmp-norbert/site"))
import numpy as np, soundfile as sf, psutil
import norbert
from scipy.signal import stft, istft
from music_analyzer.common import project_root, read_json, write_json
from music_analyzer.commercial_eval import load_model, db, stem_metrics
from music_analyzer.roformer_runner import overlap_infer
import torch

base = project_root(); REF = base / "data/pad-eval/cases-v16"
CASES = "pad00-mix pad00-quiet pad01-mix pad01-nopad pad02-mix pad03-mix pad04-mix pad05-mix pad06-mix pad07-mix".split()
FAMS = ("piano", "guitar", "bass", "drums"); OTHER = ("strings", "brass", "synth"); NP, NO = 2048, 1536
read = lambda p: sf.read(p, dtype="float32", always_2d=True)[0]
model, reg, chunk = load_model("bs_roformer_core4"); process = psutil.Process()


def infer(piece):
    with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
        return model(torch.from_numpy(piece).unsqueeze(0).cuda())[0].float().cpu().numpy()


def to_tfc(audio):  # (n, 2) -> (frames, bins, 2)
    _, _, z = stft(audio.T, nperseg=NP, noverlap=NO)
    return np.transpose(z, (2, 1, 0))


def from_tfc(z, n):
    _, x = istft(np.transpose(z, (2, 1, 0)), nperseg=NP, noverlap=NO)
    return x.T[:n].astype(np.float32)


def image(a):  # stereo image descriptors: inter-channel correlation and L/R level difference (dB)
    c = float(np.corrcoef(a[:, 0], a[:, 1])[0, 1]) if np.any(a) else 0.
    return c, db(a[:, 0]) - db(a[:, 1])


def refine(variant, estimates, mix):
    n = len(mix); x = to_tfc(mix); residual = mix - sum(estimates.values())
    names = list(estimates)
    use5 = variant != "C4_wiener1_4src"
    sources = [estimates[k] for k in names] + ([residual] if use5 else [])
    v = np.stack([np.abs(to_tfc(s)) for s in sources], axis=-1)  # (frames, bins, ch, sources)
    if variant == "B_ratio_mask":
        y = norbert.softmask(v, x)
    else:
        y = norbert.wiener(v, x, iterations=2 if variant == "D_wiener2" else 1, use_softmask=True)
    out = {k: from_tfc(y[..., i], n) for i, k in enumerate(names)}
    out["other"] = mix - sum(out.values())  # exact partition
    return out


VARIANTS = ("A_raw", "B_ratio_mask", "C_wiener1", "D_wiener2", "C4_wiener1_4src")
rows = []
for case in CASES:
    refs = {f: (read(REF / case / "evaluation-references" / f"{f}.wav") if (REF / case / "evaluation-references" / f"{f}.wav").exists() else None) for f in (*FAMS, *OTHER)}
    mix = read(Path(read_json(REF / case / "prepared.json")["input"])); n = min(len(mix), *[len(v) for v in refs.values() if v is not None]); mix = mix[:n]
    est = overlap_infer(mix.T.copy(), chunk, .4, infer, output_stems=4)
    raw = {f: e.T[:n] for f, e in zip(reg["source_labels"], est)}
    sources = {k: v[:n] for k, v in refs.items() if v is not None}
    other_ref = sum((sources[k] for k in OTHER if k in sources), np.zeros_like(mix))
    for variant in VARIANTS:
        started = time.perf_counter(); rss0 = process.memory_info().rss
        out = {**raw, "other": mix - sum(raw.values())} if variant == "A_raw" else refine(variant, raw, mix)
        seconds = time.perf_counter() - started; rss = (process.memory_info().rss - rss0) / 2 ** 20
        sum_err = float(np.max(np.abs(sum(out.values()).astype(np.float64) - mix)))
        for fam in (*FAMS, "other"):
            target = other_ref if fam == "other" else sources.get(fam)
            if target is None or not np.any(target):
                continue
            m = stem_metrics(target, out[fam], [v for k, v in sources.items() if k != fam and not (fam == "other" and k in OTHER)])
            (tc, tl), (ec, el) = image(target), image(out[fam])
            rows.append({"case": case, "variant": variant, "stem": fam, **m, "image_corr_err": abs(tc - ec), "image_lr_db_err": abs(tl - el),
                         "sum_error": sum_err, "cpu_seconds": seconds, "rss_delta_mb": rss})
    print("wiener", case, flush=True)

# absent-stem false positives (one target removed)
absent = []
for t in range(4):
    src = {f: read(base / "data/pad-eval/stems" / f"{f}-{t:02d}.wav") * .5 for f in (*FAMS, "strings", "brass")}
    n = min(len(v) for v in src.values())
    for target in FAMS:
        mix = sum(v[:n] for k, v in src.items() if k != target)
        est = overlap_infer(mix.T.copy(), chunk, .4, infer, output_stems=4)
        raw = {f: e.T[:n] for f, e in zip(reg["source_labels"], est)}
        for variant in VARIANTS:
            out = raw if variant == "A_raw" else refine(variant, raw, mix)
            absent.append({"variant": variant, "absent": target, "fp_db_re_mix": db(out[target]) - db(mix)})
summary = {}
for variant in VARIANTS:
    for fam in (*FAMS, "other"):
        sel = [r for r in rows if r["variant"] == variant and r["stem"] == fam]
        summary[f"{variant}|{fam}"] = {k: float(np.mean([r[k] for r in sel])) for k in ("sdr", "si_sdr", "leak_db", "missing_db", "image_corr_err", "image_lr_db_err")} | {"n": len(sel)}
    sel = [r for r in rows if r["variant"] == variant]
    summary[f"{variant}|_cost"] = {"cpu_seconds_per_15s": float(np.mean([r["cpu_seconds"] for r in sel])), "rss_delta_mb": float(max(r["rss_delta_mb"] for r in sel)),
                                    "sum_error_max": float(max(r["sum_error"] for r in sel)),
                                    "absent_fp_db": float(np.mean([r["fp_db_re_mix"] for r in absent if r["variant"] == variant]))}
write_json(base / "docs/COMMERCIAL_CLEAN_WIENER_RESULTS.json", {"summary": summary, "rows": rows, "absent": absent,
          "norbert": {"version": "0.2.1", "license": "MIT (Inria; LICENSE shipped in the wheel)", "wheel_sha256": "409ac3f173cfb1fdaad21563b8f730d7cbe01af81349bcd96fb2b8b9d5f74339",
                      "requires": ["scipy"], "source": "https://github.com/sigsep/norbert"}})
print("WIENER DONE", flush=True)
