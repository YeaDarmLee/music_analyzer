"""CLAPSep replacement candidates for piano->drums cymbal transfer, on license-clean synthetic GT.

Evidence candidates (all from official Mega53 heads or DSP, no CLAPSep/LAION-CLAP):
  C0 none | C1 DSP only (HPSS x high-frequency) | C2 hh head | C3 percussion head | C4 drums head | C5 hh+percussion
Pipeline: core4 on mix -> piano/drums estimates -> cymbal_extract(piano, evidence) -> piano-moved / drums+moved (sum preserved).
Output: docs/COMMERCIAL_CLEAN_CYMBAL_RESULTS.json
"""
import copy
import numpy as np, soundfile as sf, torch
from music_analyzer.common import project_root, read_json, write_json, sha256_file
from music_analyzer.commercial_eval import load_model, run, db, raw_sdr, si_sdr
from music_analyzer.mega53_experiment import configuration, prune_heads, CHECKPOINT_SHA
from music_analyzer.piano_drum_refinement import cymbal_extract
from music_analyzer.vendor.msst.bs_roformer import BSRoformer

base = project_root(); gt = base / "data/commercial-eval/cymbal-gt"
labels = configuration()["training"]["instruments"]
HEADS = ("hh", "percussion", "drums")
source = base / "data/separation/models/mega53_3head/official-53.ckpt"
assert sha256_file(source) == CHECKPOINT_SHA
cfg = copy.deepcopy(configuration()); cfg["model"]["num_stems"] = len(HEADS)
weights = prune_heads(torch.load(source, map_location="cpu", weights_only=True), tuple(labels.index(h) for h in HEADS))
evidence_model = BSRoformer(**cfg["model"]); evidence_model.load_state_dict(weights, strict=True); evidence_model.eval().cuda()
core, reg, chunk = load_model("bs_roformer_core4")


def rd(p):
    return sf.read(p, dtype="float32", always_2d=True)[0]


def project_db(est, ref_a, ref_b):
    e = est.ravel().astype(np.float64)
    def ex(r):
        r = r.ravel().astype(np.float64); c = np.dot(e, r) / (np.dot(r, r) + 1e-12); return float(np.sum((c * r) ** 2))
    return float(10 * np.log10((ex(ref_a) + 1e-12) / (ex(ref_b) + 1e-12)))


rows = []
for case in sorted(p for p in gt.iterdir() if p.is_dir()):
    piano, cym, body, mix = (rd(case / f"{k}.wav") for k in ("piano", "cymbals", "body", "mix"))
    est = run(core, chunk, reg["source_labels"], mix); p_est, d_est = est["piano"], est["drums"]
    ev = run(evidence_model, 441000, list(HEADS), mix)
    candidates = {"C0_none": None, "C1_dsp_only": True, "C2_hh": ev["hh"], "C3_percussion": ev["percussion"],
                  "C4_drums": ev["drums"], "C5_hh_plus_percussion": ev["hh"] + ev["percussion"]}
    # leak scenarios: 0 = natural estimates (no real leakage on clean synthetic data), else GT cymbals moved from drums into piano at that level
    for leak_db in (None, -12, -6):
        leak = np.zeros_like(p_est) if leak_db is None else cym * 10 ** (leak_db / 20)
        p_in, d_in = p_est + leak, d_est - leak
        for name, e in candidates.items():
            evidence = None if e is None else (p_in * 1e3 if name == "C1_dsp_only" else e)
            moved = np.zeros_like(p_in) if evidence is None else cymbal_extract(p_in, evidence)
            p_new, d_new = p_in - moved, d_in + moved
            sum_error = float(np.max(np.abs((p_new + d_new).astype(np.float64) - p_in - d_in)))
            rows.append({"case": case.name, "leak_db": leak_db, "approach": name, "piano_sdr": raw_sdr(piano, p_new), "piano_si_sdr": si_sdr(piano, p_new),
                         "drums_sdr": raw_sdr(cym + body, d_new), "cymbal_in_piano_db": project_db(p_new, cym, piano),
                         "moved_db": db(moved), "piano_db": db(p_in), "sum_error": sum_error})
    print(case.name, flush=True)
write_json(base / "docs/COMMERCIAL_CLEAN_CYMBAL_RESULTS.json", {"rows": rows, "heads": list(HEADS)})
print("CYMBAL EVAL DONE", flush=True)
