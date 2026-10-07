"""Lead/backing replacement check on the user's own Mureka AI song (no clean vocal GT exists, so metrics are GT-free).

baseline: bs_karaoke (UNKNOWN weight)   candidate: Mega53 lead-vocal/back-vocal heads (bs_roformer_vocal2)
Both receive the identical KJ vocals stem. Writes listening files + comparison.json to data/commercial-eval/vocal_split/.
"""
import json, time
import numpy as np, soundfile as sf, torch
from music_analyzer.common import project_root, write_json
from music_analyzer.commercial_eval import load_model, run, read_audio, db, partition_stats

base = project_root()
vocals = read_audio(base / "data/separation/jobs/job_e3518d8c68264a748cd3b1c419870364/result/stems/vocals.wav")
out = base / "data/commercial-eval/vocal_split"; out.mkdir(parents=True, exist_ok=True)
sf.write(out / "vocals_input.wav", vocals, 44100, subtype="FLOAT")
result = {"input": "Mureka AI song (user-owned), KJ vocals stem", "seconds": len(vocals) / 44100, "models": {}}
est = {}
for name, model_id, lead, back in (("baseline", "bs_karaoke", "lead", "backing"), ("commercial", "bs_roformer_vocal2", "lead", "backing")):
    model, reg, chunk = load_model(model_id)
    torch.cuda.synchronize(); torch.cuda.reset_peak_memory_stats(); s = time.perf_counter()
    r = run(model, 441000, reg["source_labels"], vocals, single=not reg.get("multi_output", True) and name == "baseline")  # preset segment_sec=10 for both
    torch.cuda.synchronize(); sec = time.perf_counter() - s
    mem = torch.cuda.max_memory_allocated() / 2**20
    est[name] = (r[lead], r[back])
    (out / name).mkdir(exist_ok=True)
    for label, audio in (("lead", r[lead]), ("backing", r[back])):
        sf.write(out / name / f"{label}.wav", audio, 44100, subtype="FLOAT")
    residual = vocals - r[lead] - r[back]
    result["models"][name] = {"model": model_id, "seconds": sec, "rtf": sec / (len(vocals) / 44100), "peak_vram_mb": mem,
                              "lead_db": db(r[lead]), "backing_db": db(r[back]), "vocals_db": db(vocals),
                              "residual_db_vs_vocals": db(residual) - db(vocals),
                              "backing_to_lead_db": db(r[back]) - db(r[lead])}
    del model; torch.cuda.empty_cache()
bl, bb = est["baseline"]; cl, cb = est["commercial"]
from music_analyzer.evaluation import raw_sdr, si_sdr
result["agreement"] = {"lead_sdr_commercial_vs_baseline": raw_sdr(bl, cl), "backing_sdr_commercial_vs_baseline": raw_sdr(bb, cb),
                       "note": "baseline is not ground truth; agreement only"}
# option B: single vocal (no split) = the vocals stem itself; its split-error is zero by construction
result["option_b_single_vocal"] = {"definition": "lead=vocals stem, no backing", "residual_db": None}
write_json(out / "comparison.json", result)
print(json.dumps(result, indent=1, ensure_ascii=False))
