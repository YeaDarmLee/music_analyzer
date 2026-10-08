"""Summarize a run's metrics.jsonl at the observation steps (default 5k/10k/20k/final) + throughput/telemetry.
usage: python scripts/train_summary.py runs/<run_id> [step ...]"""
import json
import sys
from pathlib import Path

run = Path(sys.argv[1])
steps = [int(x) for x in sys.argv[2:]] or [5000, 10000, 20000, 37500]
ev = [json.loads(l) for l in (run / "metrics.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
val = {e["step"]: e for e in ev if e["event"] == "val"}
train = [e for e in ev if e["event"] == "train"]
KEYS = ["val_loss", "val_sdr", "val_si_sdr", "val_sdr_vocals", "val_sdr_instrumental", "val_si_sdr_vocals", "val_si_sdr_instrumental",
        "val_inactive_rms_ratio_db", "val_recon_err_db"]
print("val steps available:", sorted(val))
for s in steps:
    v = val.get(s) or val.get(max([k for k in val if k <= s], default=None))
    if not v:
        print(f"--- step {s}: no validation yet")
        continue
    print(f"--- val @ step {v['step']}")
    for k in KEYS:
        print(f"  {k:28s} {v.get(k)}")
    for g in ("category", "singer"):
        for k in sorted(x for x in v if x.startswith(f"val_{g}/") and x.endswith("/si_sdr")):
            n = v.get(k[:-len('/si_sdr')] + "/n")
            print(f"  {k[4:]:34s} si_sdr={v[k]:.2f} sdr={v.get(k[:-6] + 'sdr'):.2f} inactive_db={v.get(k[:-6] + 'inactive_rms_db'):.1f} n={n}")
if train:
    last = train[-200:]
    f = lambda k: [e[k] for e in last if e.get(k) is not None]
    mean = lambda xs: sum(xs) / len(xs) if xs else None
    print("--- last <=200 train steps: step", train[-1]["step"], "epoch", train[-1].get("epoch"), "loss", mean(f("loss")),
          "chunks/s", mean(f("chunks_per_s")), "step_s", mean(f("step_s")), "data_wait_s/step", mean(f("data_wait_s")),
          "cache_hit", mean(f("cache_hit_rate")), "item_load_s", mean(f("item_load_s")), "gpu%", mean(f("gpu_util_pct")),
          "cpu%", mean(f("cpu_util_pct")), "peak_vram_mib", max(f("peak_vram_mib") or [0]))
