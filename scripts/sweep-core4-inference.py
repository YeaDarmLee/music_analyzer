"""Phase A: inference-parameter-only sweep for bs_roformer_core4 (weights, routing, RULES, STRENGTH untouched).

Parameters the runner really supports (roformer_runner.run_roformer / overlap_infer): segment_sec (chunk), overlap (stride = chunk*(1-overlap)),
fp16 autocast (hard-coded in infer). The crossfade window is fixed (10% linear fade), batch is 1, there is no shift/TTA for RoFormer
(`shifts` is the Demucs path). 'tta_swap' below is an EXPERIMENT that does not exist in production: average of est(x) and swap_lr(est(swap_lr(x))).

usage: sweep-core4-inference.py [name ...]   (default: all)  -> docs/COMMERCIAL_CLEAN_SWEEP_RESULTS.json
Quick benchmark: 10 GeneralUser GS pad cases (clean mix as input; the real pipeline instrumental behaves the same, see SIX_DIAGNOSIS part 2)
plus an absent-stem test (8 timbres x 4 targets).
"""
import sys, time
from pathlib import Path
import numpy as np, soundfile as sf, torch
from music_analyzer.common import project_root, read_json, write_json
from music_analyzer.commercial_eval import load_model, db, stem_metrics
from music_analyzer.roformer_runner import overlap_infer

base = project_root(); REF = base / "data/pad-eval/cases-v16"; OUT = base / "docs/COMMERCIAL_CLEAN_SWEEP_RESULTS.json"
CASES = "pad00-mix pad00-quiet pad01-mix pad01-nopad pad02-mix pad03-mix pad04-mix pad05-mix pad06-mix pad07-mix".split()
FAMS = ("piano", "guitar", "bass", "drums"); OTHER = ("strings", "brass", "synth"); ALL = (*FAMS, *OTHER)
read = lambda p: sf.read(p, dtype="float32", always_2d=True)[0]
# name: (model, segment_sec, overlap, fp16, tta_swap)
CONFIGS = {
    "baseline_6s_prod(13.35s,.4)": ("bs_roformer_6s", 13.351473922902494, .4, True, False),
    "core4_prod(10s,.4,fp16)": ("bs_roformer_core4", 10, .4, True, False),
    "core4_ov.25": ("bs_roformer_core4", 10, .25, True, False),
    "core4_ov.5": ("bs_roformer_core4", 10, .5, True, False),
    "core4_ov.6": ("bs_roformer_core4", 10, .6, True, False),
    "core4_ov.75": ("bs_roformer_core4", 10, .75, True, False),
    "core4_seg7": ("bs_roformer_core4", 7, .4, True, False),
    "core4_seg12": ("bs_roformer_core4", 12, .4, True, False),
    "core4_seg15": ("bs_roformer_core4", 15, .4, True, False),
    "core4_fp32": ("bs_roformer_core4", 10, .4, False, False),
    "core4_ov.75_fp32": ("bs_roformer_core4", 10, .75, False, False),
    "core4_tta_swap(experimental)": ("bs_roformer_core4", 10, .4, True, True),
}
wanted = sys.argv[1:] or list(CONFIGS)
results = read_json(OUT) if OUT.exists() else {}
loaded = {}


def separate(model, chunk_sec, overlap, fp16, tta, labels, audio):
    chunk = round(chunk_sec * 44100)
    def infer(piece):
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16, enabled=fp16):
            return model(torch.from_numpy(piece).unsqueeze(0).cuda())[0].float().cpu().numpy()
    est = overlap_infer(audio.T.copy(), chunk, overlap, infer, output_stems=len(labels))
    if tta:
        swapped = overlap_infer(audio[:, ::-1].T.copy(), chunk, overlap, infer, output_stems=len(labels))
        est = (est + swapped[:, ::-1, :]) / 2
    return {l: e.T for l, e in zip(labels, est)}


for name in wanted:
    model_id, seg, overlap, fp16, tta = CONFIGS[name]
    if model_id not in loaded:
        loaded.clear(); torch.cuda.empty_cache(); loaded[model_id] = load_model(model_id)
    model, reg, _ = loaded[model_id]; labels = reg["source_labels"]
    rows, seconds, audio_seconds = [], 0., 0.
    torch.cuda.synchronize(); torch.cuda.reset_peak_memory_stats()
    for case in CASES:
        refs = {f: (read(REF / case / "evaluation-references" / f"{f}.wav") if (REF / case / "evaluation-references" / f"{f}.wav").exists() else None) for f in ALL}
        mix = read(Path(read_json(REF / case / "prepared.json")["input"])); n = min(len(mix), *[len(v) for v in refs.values() if v is not None]); mix = mix[:n]
        started = time.perf_counter(); est = separate(model, seg, overlap, fp16, tta, labels, mix); torch.cuda.synchronize()
        seconds += time.perf_counter() - started; audio_seconds += n / 44100
        sel = {f: est[f][:n] for f in FAMS}; sel["other"] = mix - sum(sel.values())
        other_ref = sum((refs[f][:n] for f in OTHER if refs[f] is not None), np.zeros_like(mix))
        sources = {k: v[:n] for k, v in refs.items() if v is not None}
        for fam in (*FAMS, "other"):
            target = other_ref if fam == "other" else refs[fam][:n] if refs[fam] is not None else None
            if target is None or not np.any(target):
                continue
            rows.append({"case": case, "stem": fam, **stem_metrics(target, sel[fam], [v for k, v in sources.items() if k != fam])})
        rows.append({"case": case, "stem": "_sum", "sum_error": float(np.max(np.abs(sum(sel.values()).astype(np.float64) - mix)))})
    vram = torch.cuda.max_memory_allocated() / 2 ** 20
    absent = []
    for t in range(8):
        src = {f: read(base / "data/pad-eval/stems" / f"{f}-{t:02d}.wav") * .5 for f in (*FAMS, "strings", "brass")}
        n = min(len(v) for v in src.values())
        for target in FAMS:
            mix = sum(v[:n] for k, v in src.items() if k != target)
            est = separate(model, seg, overlap, fp16, tta, labels, mix)
            absent.append(db(est[target]) - db(mix))
    summary = {}
    for fam in (*FAMS, "other"):
        sel = [r for r in rows if r["stem"] == fam]
        summary[fam] = {k: float(np.mean([r[k] for r in sel])) for k in ("sdr", "si_sdr", "est_vs_ref_db", "leak_db", "missing_db")} | {"n": len(sel)}
    results[name] = {"model": model_id, "segment_sec": seg, "overlap": overlap, "fp16": fp16, "tta_swap": tta, "summary": summary,
                     "absent_fp_db": float(np.mean(absent)), "absent_fp_db_by_target": {f: float(np.mean(absent[i::4])) for i, f in enumerate(FAMS)},
                     "sum_error_max": max(r["sum_error"] for r in rows if r["stem"] == "_sum"),
                     "seconds_per_audio_minute": seconds / audio_seconds * 60, "peak_vram_mb": vram}
    write_json(OUT, results); print(name, {f: round(v["sdr"], 2) for f, v in summary.items()}, round(results[name]["absent_fp_db"], 1), flush=True)
print("SWEEP DONE", flush=True)
