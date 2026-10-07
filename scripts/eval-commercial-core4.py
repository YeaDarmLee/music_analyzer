"""Model-level A/B: bs_6stem_fixed (baseline, UNKNOWN weight) vs Mega53 core4 heads (candidate) on license-clean synthetic GT.

Data: data/pad-eval/stems (FluidSynth + GeneralUser GS renders, numpy pads) - no MedleyDB, no commercial songs.
Both models get the same non-vocal mix. Ratios sweep one target stem at 0/-6/-12/-18 dB (and absent) against the rest.
Output: docs/COMMERCIAL_CLEAN_CORE4_RESULTS.json
"""
import json, sys, time
import numpy as np, soundfile as sf, torch
from music_analyzer.common import project_root, read_json, write_json
from music_analyzer.evaluation import raw_sdr, si_sdr
from music_analyzer.roformer_runner import load_config, overlap_infer
from music_analyzer.vendor.msst.bs_roformer import BSRoformer

base = project_root(); stems_dir = base / "data/pad-eval/stems"
FAMS = ("piano", "guitar", "bass", "drums")
OTHERS = ("strings", "brass")  # always present, never a target of the 4-head model
TIMBRES = [int(a) for a in sys.argv[1].split(",")] if len(sys.argv) > 1 else [0, 1, 2, 3, 4, 5, 6, 7]
RATIOS = (0, -6, -12, -18, None)  # None = target absent (silence false-positive test)
GAIN = .5


def load_model(model_id):
    reg = read_json(base / f"data/separation/models/{model_id}/registration.json")
    cfg = load_config(reg)
    model = BSRoformer(**cfg["model"])
    w = torch.load(base / "data/separation/models" / model_id / reg["checkpoint_filename"], map_location="cpu", weights_only=True)
    w = w.get("state_dict", w)
    model.load_state_dict(w, strict=True); model.eval().cuda()
    return model, reg, cfg["audio"]["chunk_size"]


def run(model, chunk, labels, mix):
    def infer(piece):
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
            return model(torch.from_numpy(piece).unsqueeze(0).cuda())[0].float().cpu().numpy()
    est = overlap_infer(mix.T.copy(), chunk, .4, infer, output_stems=len(labels))
    return {l: e.T for l, e in zip(labels, est)}


def projection_leak_db(est, refs, target):
    """Energy of the estimate explained (least squares, per source) by non-target sources vs by the target."""
    e = est.ravel().astype(np.float64)
    def explained(r):
        r = r.ravel().astype(np.float64); c = np.dot(e, r) / (np.dot(r, r) + 1e-12); return float(np.sum((c * r) ** 2))
    own = explained(refs[target]); other = sum(explained(r) for k, r in refs.items() if k != target)
    return float(10 * np.log10((other + 1e-12) / (own + 1e-12)))


def db(x):
    return float(20 * np.log10(np.sqrt(np.mean(np.asarray(x, np.float64) ** 2)) + 1e-12))


models = {"baseline_6s": load_model("bs_roformer_6s"), "core4": load_model("bs_roformer_core4")}
rows = []; timing = {k: {"seconds": 0., "audio_seconds": 0., "peak_vram_mb": 0.} for k in models}
for t in TIMBRES:
    src = {f: sf.read(stems_dir / f"{f}-{t:02d}.wav", dtype="float32", always_2d=True)[0] * GAIN for f in (*FAMS, *OTHERS)}
    n = min(len(v) for v in src.values()); src = {k: v[:n] for k, v in src.items()}
    for target in FAMS:
        for ratio in RATIOS:
            refs = dict(src)
            refs[target] = src[target] * (0. if ratio is None else 10 ** (ratio / 20))
            mix = sum(refs.values())
            for name, (model, reg, chunk) in models.items():
                torch.cuda.synchronize(); torch.cuda.reset_peak_memory_stats(); s = time.perf_counter()
                est = run(model, chunk, reg["source_labels"], mix)
                torch.cuda.synchronize()
                timing[name]["seconds"] += time.perf_counter() - s; timing[name]["audio_seconds"] += n / 44100
                timing[name]["peak_vram_mb"] = max(timing[name]["peak_vram_mb"], torch.cuda.max_memory_allocated() / 2**20)
                sel = {f: est[f] for f in FAMS}
                residual = mix - sum(sel.values())
                row = {"timbre": t, "target": target, "ratio_db": ratio, "model": name,
                       "finite": bool(all(np.isfinite(v).all() for v in sel.values())), "residual_db": db(residual), "mix_db": db(mix)}
                if ratio is None:
                    row["silence_false_positive_db"] = db(sel[target]) - db(mix)  # relative to mix; very negative is good
                else:
                    r = refs[target]; e = sel[target]
                    row.update(sdr=raw_sdr(r, e), si_sdr=si_sdr(r, e), leak_db=projection_leak_db(e, {**refs, **{}}, target),
                               energy_ratio_db=db(e) - db(r))
                rows.append(row)
    print("timbre", t, flush=True)
write_json(base / "docs/COMMERCIAL_CLEAN_CORE4_RESULTS.json", {"rows": rows, "timing": timing, "timbres": TIMBRES, "gain": GAIN})
print("CORE4 EVAL DONE", len(rows), flush=True)
