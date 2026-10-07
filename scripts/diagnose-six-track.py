"""Diagnose where commercial_6 / commercial_13 lose SDR versus the final_11 / basic_6 baseline. Diagnosis only: nothing is tuned.

part1  head-pruning fidelity: official Mega53 (53 heads) vs derived core4, same input, fp32 and fp16
part2  raw model SDR: bs_6stem_fixed vs core4 on (a) clean GT instrumental, (b) the instrumental the real pipeline produced; final stems vs raw
part3  stage trace of commercial_13 stems (raw core4 -> each intermediate file -> final)
part4  absent-stem false positive (model level; commercial_6 has no post step, see part2 'final_vs_raw_max_abs')
usage: diagnose-six-track.py [1] [2] [3] [4]   -> docs/COMMERCIAL_CLEAN_SIX_DIAGNOSIS.json (parts merge into it)
"""
import gc, glob, json, os, sys
from pathlib import Path
import numpy as np, soundfile as sf, torch
from music_analyzer.common import project_root, read_json, write_json, sha256_file
from music_analyzer.evaluation import raw_sdr, si_sdr
from music_analyzer.commercial_eval import load_model, run, db
from music_analyzer.mega53_experiment import configuration, CHECKPOINT_SHA
from music_analyzer.roformer_runner import overlap_infer
from music_analyzer.vendor.msst.bs_roformer import BSRoformer

base = project_root(); REF = base / "data/pad-eval/cases-v16"; OUT = base / "docs/COMMERCIAL_CLEAN_SIX_DIAGNOSIS.json"
CASES = "pad00-mix pad00-quiet pad01-mix pad01-nopad pad02-mix pad03-mix pad04-mix pad05-mix pad06-mix pad07-mix".split()
FAMS = ("piano", "guitar", "bass", "drums"); OTHER = ("strings", "brass", "synth"); ALL = (*FAMS, *OTHER)
read = lambda p: sf.read(p, dtype="float32", always_2d=True)[0]
parts = sys.argv[1:] or ["1", "2", "3", "4"]
out = read_json(OUT) if OUT.exists() else {}


def refs_for(case):
    d = REF / case / "evaluation-references"
    return {f: (read(d / f"{f}.wav") if (d / f"{f}.wav").exists() else None) for f in ALL}


def explained(e, r):
    r = r.ravel().astype(np.float64); e = e.ravel().astype(np.float64)
    return float((np.dot(e, r) / (np.dot(r, r) + 1e-12)) ** 2 * np.dot(r, r))


def metrics(target, est, refs, name):
    """sdr/si_sdr; est_vs_ref_db = estimate energy re reference; leak_db = energy explained by other GT sources vs own (lower is better);
    missing_db = target energy not reproduced by the best scalar fit of the estimate, 10log10(|t-fit|^2/|t|^2) (lower is better)."""
    t = target.astype(np.float64); e = est.astype(np.float64)
    fit = (np.dot(t.ravel(), e.ravel()) / (np.dot(e.ravel(), e.ravel()) + 1e-12)) * e
    others = sum(explained(est, r[: len(est)]) for k, r in refs.items() if r is not None and k != name and np.any(r))
    return {"sdr": raw_sdr(target, est), "si_sdr": si_sdr(target, est), "est_vs_ref_db": db(est) - db(target),
            "leak_db": float(10 * np.log10((others + 1e-12) / (explained(est, target) + 1e-12))),
            "missing_db": float(10 * np.log10((np.sum((t - fit) ** 2) + 1e-12) / (np.sum(t ** 2) + 1e-12)))}


def avg(rows, key):
    v = [r[key] for r in rows if r.get(key) is not None and np.isfinite(r[key])]
    return float(np.mean(v)) if v else None


KEYS = ("sdr", "si_sdr", "est_vs_ref_db", "leak_db", "missing_db")

if "1" in parts:
    cfg = configuration(); labels = cfg["training"]["instruments"]
    source = base / "data/separation/models/mega53_3head/official-53.ckpt"
    assert sha256_file(source) == CHECKPOINT_SHA
    reg = read_json(base / "data/separation/models/bs_roformer_core4/registration.json")
    derivation = read_json(base / "separation/configs/models/bs_roformer_core4.json")["derivation"]
    idx = [int(k) for k in derivation["selected_heads"]]  # official head indexes, in core4 output order
    names = [labels[i] for i in idx]
    official = BSRoformer(**cfg["model"]); w = torch.load(source, map_location="cpu", weights_only=True)
    official.load_state_dict(w.get("state_dict", w), strict=True); official.eval()
    core4, creg, chunk = load_model("bs_roformer_core4"); core4.cpu()
    result = {"selected_heads": names, "official_indexes": idx, "core4_labels": creg["source_labels"], "inputs": {}}
    for case in ("pad00-mix", "pad03-mix", "pad06-mix"):
        mix = read(Path(read_json(REF / case / "prepared.json")["input"]))[: 44100 * 12]
        item = {}
        for precision in ("fp32", "fp16"):
            def make(model):
                def infer(piece):
                    with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16, enabled=precision == "fp16"):
                        return model(torch.from_numpy(piece).unsqueeze(0).cuda())[0].float().cpu().numpy()
                return infer
            core4.cuda(); core = overlap_infer(mix.T.copy(), chunk, .4, make(core4), output_stems=len(idx)); core4.cpu(); torch.cuda.empty_cache()
            official.cuda(); full = overlap_infer(mix.T.copy(), chunk, .4, make(official), output_stems=53); official.cpu(); torch.cuda.empty_cache()
            for i, fam in enumerate(creg["source_labels"]):
                a = full[idx[i]].T; b = core[i].T
                item[f"{precision}:{fam}"] = {"max_abs_err": float(np.max(np.abs(a - b))), "rms_err": float(np.sqrt(np.mean((a - b) ** 2))),
                    "correlation": float(np.corrcoef(a.ravel(), b.ravel())[0, 1]), "sdr_db": raw_sdr(a, b), "ref_rms": float(np.sqrt(np.mean(a ** 2)))}
        result["inputs"][case] = item; print("part1", case, flush=True)
    out["part1_fidelity"] = result
    del official, core4; gc.collect(); torch.cuda.empty_cache()

if "2" in parts:
    models = {"basic": load_model("bs_roformer_6s"), "core4": load_model("bs_roformer_core4")}
    rows = []
    for case in CASES:
        refs = refs_for(case); clean = read(Path(read_json(REF / case / "prepared.json")["input"]))
        rec = next(glob.iglob(str(base / f"data/commercial-eval/six/commercial_6/libs/{case}/web/*/record.json")))
        record = json.loads(Path(rec).read_text(encoding="utf8")); root = Path(rec).parents[2]
        inst = read(root / record["instrumental"])
        finals = {t["family"]: read(root / t["path"]) for t in record["tracks"]}
        other_ref = sum((refs[f] for f in OTHER if refs[f] is not None), np.zeros_like(clean))
        for name, (model, reg, chunk) in models.items():
            for source, audio in (("clean_mix", clean), ("pipeline_instrumental", inst)):
                n = min(len(audio), len(other_ref)); audio = audio[:n]
                est = run(model, chunk, reg["source_labels"], audio)
                sel = {f: est[f][:n] for f in FAMS}; sel["other"] = audio - sum(sel.values())
                for fam in (*FAMS, "other"):
                    target = other_ref[:n] if fam == "other" else refs[fam][:n]
                    if not np.any(target):
                        continue
                    m = metrics(target, sel[fam], {k: (v[:n] if v is not None else None) for k, v in refs.items()}, fam)
                    row = {"case": case, "model": name, "input": source, "stem": fam, **m}
                    if name == "core4" and source == "pipeline_instrumental" and fam in finals:
                        row["final_vs_raw_max_abs"] = float(np.max(np.abs(finals[fam][:n] - sel[fam])))
                    rows.append(row)
        print("part2", case, flush=True)
    summary = {}
    for name in models:
        for source in ("clean_mix", "pipeline_instrumental"):
            for fam in (*FAMS, "other"):
                sel = [r for r in rows if r["model"] == name and r["input"] == source and r["stem"] == fam]
                if sel:
                    summary[f"{name}|{source}|{fam}"] = {k: avg(sel, k) for k in KEYS} | {"n": len(sel)}
    out["part2_raw"] = {"rows": rows, "summary": summary,
                        "final_vs_raw_max_abs": max((r.get("final_vs_raw_max_abs") or 0) for r in rows)}
    del models; gc.collect(); torch.cuda.empty_cache()

if "3" in parts:
    steps = {}
    for case in CASES:
        refs = refs_for(case); lib = base / "data/commercial-eval/pad" / case / "library"
        rec = next(glob.iglob(str(lib / "web/*/record.json"))); record = json.loads(Path(rec).read_text(encoding="utf8")); web = Path(rec).parent
        raw = {}
        for job_id in record["job_ids"]:
            job = read_json(lib / "jobs" / job_id / "job.json")
            if job["model_id"] == "bs_roformer_core4":
                manifest = read_json(lib / "jobs" / job_id / "result/manifest.json")
                raw = {s["family"]: lib / "jobs" / job_id / "result" / s["path"] for s in manifest["stems"]}
        for fam in ("drums", "piano", "bass", "strings"):
            target = refs[fam]
            if target is None:
                continue
            seq = [("raw_core4", raw[fam])] if fam in raw else []
            seq += [(p.stem.replace(fam + "-", ""), p) for p in sorted(web.glob(f"{fam}-*.wav"), key=os.path.getmtime)]
            seq.append(("final", lib / next(t for t in record["tracks"] if t["family"] == fam)["path"]))
            for label, path in seq:
                a = read(path)[: len(target)]
                steps.setdefault(fam, {}).setdefault(label, []).append(metrics(target[: len(a)], a, refs, fam))
        print("part3", case, flush=True)
    out["part3_trace"] = {fam: {label: {k: avg(rows, k) for k in KEYS} | {"n": len(rows)} for label, rows in d.items()} for fam, d in steps.items()}

if "4" in parts:
    models = {"basic": load_model("bs_roformer_6s"), "core4": load_model("bs_roformer_core4")}
    stems = base / "data/pad-eval/stems"; rows = []
    for t in range(8):
        src = {f: read(stems / f"{f}-{t:02d}.wav") * .5 for f in (*FAMS, "strings", "brass")}
        n = min(len(v) for v in src.values()); src = {k: v[:n] for k, v in src.items()}
        for target in FAMS:
            mix = sum(v for k, v in src.items() if k != target)
            for name, (model, reg, chunk) in models.items():
                est = run(model, chunk, reg["source_labels"], mix)
                rows.append({"timbre": t, "absent": target, "model": name, "fp_db_re_mix": db(est[target]) - db(mix)})
        print("part4", t, flush=True)
    out["part4_absent"] = {"rows": rows, "summary": {f"{m}|{f}": float(np.mean([r["fp_db_re_mix"] for r in rows if r["model"] == m and r["absent"] == f])) for m in models for f in FAMS}}

if "5" in parts:  # strings/other ablation: same mega5 on residuals produced by different 4-instrument stages (no routing)
    models = {"basic": load_model("bs_roformer_6s"), "core4": load_model("bs_roformer_core4")}
    mega5, reg5, chunk5 = load_model("bs_roformer_mega5"); rows = []
    for case in CASES:
        refs = refs_for(case)
        if refs["strings"] is None or not np.any(refs["strings"]):
            continue
        clean = read(Path(read_json(REF / case / "prepared.json")["input"])); n = min(len(clean), len(refs["strings"]))
        clean = clean[:n]
        residuals = {"oracle_gt_residual": clean - sum(refs[f][:n] for f in FAMS if refs[f] is not None)}
        for name, (model, reg, chunk) in models.items():
            est = run(model, chunk, reg["source_labels"], clean)
            residuals[name] = clean - sum(est[f][:n] for f in FAMS)
        for source, residual in residuals.items():
            est5 = run(mega5, chunk5, reg5["source_labels"], residual)
            key = "bowed_strings" if "bowed_strings" in est5 else next(k for k in est5 if "string" in k)
            rows.append({"case": case, "residual_from": source, **metrics(refs["strings"][:n], est5[key][:n], {k: (v[:n] if v is not None else None) for k, v in refs.items()}, "strings")})
        print("part5", case, flush=True)
    out["part5_strings_ablation"] = {s_: {k: avg([r for r in rows if r["residual_from"] == s_], k) for k in KEYS} | {"n": len([r for r in rows if r["residual_from"] == s_])} for s_ in ("oracle_gt_residual", "basic", "core4")}
write_json(OUT, out)
print("DIAGNOSIS DONE", parts, flush=True)
