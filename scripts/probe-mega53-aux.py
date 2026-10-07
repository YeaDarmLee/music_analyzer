"""Phase B: do the other 49 official Mega53 heads carry evidence for energy that core4 missed?

Head names come from the official config (training.instruments), read at run time; candidate groups below only reference names that exist there.
Per target stem (piano/guitar/bass/drums), on the 10 GeneralUser GS pad cases:
  corr_gt          correlation(aux_sum, GT target)
  recall_db        energy of GT target missed by core4 (GT - core4) that the aux sum explains by least-squares projection, relative to the missing energy (higher = more of the miss is visible)
  fp_db            energy of aux_sum explained by non-target GT sources vs by the target (lower is better)
  moved trial      residual R = mix - sum(core4 stems); moved = R * min(1, |STFT(aux)|/|STFT(R)|) is moved from 'other' into the stem (sum preserved exactly)
                   -> SDR of the stem and of 'other' before/after, sum error
Nothing here changes production; it is evidence only.   Output: docs/COMMERCIAL_CLEAN_AUX_RESULTS.json
"""
from pathlib import Path
import numpy as np, soundfile as sf, torch
from scipy.signal import stft, istft
from music_analyzer.common import project_root, read_json, write_json, sha256_file
from music_analyzer.commercial_eval import db, stem_metrics
from music_analyzer.mega53_experiment import configuration, CHECKPOINT_SHA
from music_analyzer.roformer_runner import overlap_infer
from music_analyzer.vendor.msst.bs_roformer import BSRoformer

base = project_root(); REF = base / "data/pad-eval/cases-v16"
CASES = "pad00-mix pad00-quiet pad01-mix pad01-nopad pad02-mix pad03-mix pad04-mix pad05-mix pad06-mix pad07-mix".split()
FAMS = ("piano", "guitar", "bass", "drums"); OTHER = ("strings", "brass", "synth")
CORE = {"piano": 33, "guitar": 20, "bass": 4, "drums": 15}
GROUPS = {  # names exist in the official config; checked below
    "drums": ["kick", "snare", "toms", "hh", "percussion", "tambourine", "congas", "timpani", "triangle"],
    "bass": ["double-bass"],
    "piano": ["digital-piano", "keys", "harpsichord", "organ"],
    "guitar": ["acoustic-guitar", "electric-guitar", "banjo", "mandolin", "ukulele", "dobro"],
}
read = lambda p: sf.read(p, dtype="float32", always_2d=True)[0]
cfg = configuration(); labels = cfg["training"]["instruments"]
for names in GROUPS.values():
    assert all(n in labels for n in names), names
source = base / "data/separation/models/mega53_3head/official-53.ckpt"; assert sha256_file(source) == CHECKPOINT_SHA
model = BSRoformer(**cfg["model"]); w = torch.load(source, map_location="cpu", weights_only=True)
model.load_state_dict(w.get("state_dict", w), strict=True); model.eval().cuda()


def infer(piece):
    with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
        return model(torch.from_numpy(piece).unsqueeze(0).cuda())[0].float().cpu().numpy()


def corr(a, b):
    return float(np.corrcoef(a.ravel(), b.ravel())[0, 1]) if np.any(a) and np.any(b) else None


def projected_db(missing, aux):
    m = missing.ravel().astype(np.float64); a = aux.ravel().astype(np.float64)
    explained = (np.dot(m, a) / (np.dot(a, a) + 1e-12)) ** 2 * np.dot(a, a)
    return float(10 * np.log10((explained + 1e-12) / (np.dot(m, m) + 1e-12)))


def move(residual, aux):
    f, t, R = stft(residual.T, nperseg=2048, noverlap=1536); _, _, A = stft(aux.T, nperseg=2048, noverlap=1536)
    gain = np.minimum(1., np.abs(A) / (np.abs(R) + 1e-9))
    _, moved = istft(R * gain, nperseg=2048, noverlap=1536)
    return moved.T[: len(residual)].astype(np.float32)


rows = []
for case in CASES:
    refs = {f: (read(REF / case / "evaluation-references" / f"{f}.wav") if (REF / case / "evaluation-references" / f"{f}.wav").exists() else None) for f in (*FAMS, *OTHER)}
    mix = read(Path(read_json(REF / case / "prepared.json")["input"])); n = min(len(mix), *[len(v) for v in refs.values() if v is not None]); mix = mix[:n]
    full = overlap_infer(mix.T.copy(), 441000, .4, infer, output_stems=53)  # (53, 2, n)
    core = {f: full[CORE[f]].T[:n] for f in FAMS}; residual = mix - sum(core.values())
    sources = {k: v[:n] for k, v in refs.items() if v is not None}
    for fam in FAMS:
        target = sources.get(fam)
        if target is None or not np.any(target):
            continue
        others = [v for k, v in sources.items() if k != fam]
        for group_name, names in {"all": GROUPS[fam], **{nm: [nm] for nm in GROUPS[fam]}}.items():
            aux = sum(full[labels.index(nm)].T[:n] for nm in names)
            missing = target - core[fam]
            row = {"case": case, "stem": fam, "group": group_name, "corr_gt": corr(aux, target), "corr_missing": corr(aux, missing),
                   "recall_db": projected_db(missing, aux),
                   "fp_db": stem_metrics(target, aux, others)["leak_db"], "aux_vs_core_db": db(aux) - db(core[fam])}
            if group_name == "all":
                moved = move(residual, aux)
                new_stem = core[fam] + moved; new_other = residual - moved
                other_ref = sum((sources[k] for k in OTHER if k in sources), np.zeros_like(mix))
                row.update(sdr_before=stem_metrics(target, core[fam], others)["sdr"], sdr_after=stem_metrics(target, new_stem, others)["sdr"],
                           other_sdr_before=stem_metrics(other_ref, residual, [v for k, v in sources.items() if k in FAMS])["sdr"],
                           other_sdr_after=stem_metrics(other_ref, new_other, [v for k, v in sources.items() if k in FAMS])["sdr"],
                           sum_error=float(np.max(np.abs((new_stem + new_other).astype(np.float64) - (core[fam] + residual)))))
            rows.append(row)
    print("aux", case, flush=True)
summary = {}
for fam in FAMS:
    for group in ["all", *GROUPS[fam]]:
        sel = [r for r in rows if r["stem"] == fam and r["group"] == group]
        if not sel:
            continue
        avg = lambda k: float(np.mean([r[k] for r in sel if r.get(k) is not None])) if any(r.get(k) is not None for r in sel) else None
        summary[f"{fam}|{group}"] = {k: avg(k) for k in ("corr_gt", "corr_missing", "recall_db", "fp_db", "aux_vs_core_db", "sdr_before", "sdr_after", "other_sdr_before", "other_sdr_after", "sum_error")} | {"n": len(sel)}
write_json(base / "docs/COMMERCIAL_CLEAN_AUX_RESULTS.json", {"head_names": labels, "groups": GROUPS, "summary": summary, "rows": rows})
print("AUX DONE", flush=True)
