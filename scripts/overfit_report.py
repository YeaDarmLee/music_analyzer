"""Overfit-test report for a finished run: per-stem SDR/SI-SDR, stem-swap check, output collapse, NaN check.

usage: python scripts/overfit_report.py runs/<experiment_id> [checkpoint_name]
Evaluates every validation scene (== training scenes for the overfit config) from the sidecar-verified checkpoint.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import engine.data.synthetic  # noqa: E402,F401
from engine.checkpoint import load_checkpoint  # noqa: E402
from engine.registry import DATASETS, build_model  # noqa: E402
from engine.training.metrics import sdr_db, si_sdr_db  # noqa: E402


def main(run_dir: str, ckpt_name: str | None = None) -> dict:
    run = Path(run_dir)
    meta = json.loads((run / "experiment.json").read_text())
    ckpt = run / (meta["checkpoints"][-1]["path"] if ckpt_name is None else f"checkpoints/{ckpt_name}")
    state, prov = load_checkpoint(ckpt)
    model_cfg, ds_cfg = meta["model_config"], json.loads(json.dumps(__import__("yaml").safe_load(
        (run / "config" / "dataset.yaml").read_text())))
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = build_model(model_cfg).to(dev).eval()
    model.load_state_dict(state["model"])
    ds = DATASETS.get(ds_cfg["kind"])(ds_cfg, model_cfg, "val", meta["seed"])
    names = model_cfg["stems"]
    rows = {n: {"sdr": [], "si_sdr": [], "cross_sdr": [], "energy_ratio": []} for n in names}
    finite = True
    for i in range(len(ds)):
        item = ds[i]
        with torch.no_grad():
            out = model(item["mix"][None].to(dev))
        for n in names:
            est, ref = out.stems[n].cpu(), item["stems"][n][None]
            finite &= bool(torch.isfinite(est).all())
            rows[n]["sdr"].append(sdr_db(est, ref).item())
            rows[n]["si_sdr"].append(si_sdr_db(est, ref).item())
            others = [m for m in names if m != n]
            rows[n]["cross_sdr"].append(max(sdr_db(est, item["stems"][m][None]).item() for m in others))
            rows[n]["energy_ratio"].append((est.pow(2).sum() / ref.pow(2).sum().clamp_min(1e-12)).item())
    mean = lambda v: sum(v) / len(v)
    rep = {"checkpoint": str(ckpt), "checkpoint_step": state["step"], "scenes": len(ds), "all_finite": finite,
           "per_stem": {n: {k: mean(v) for k, v in r.items()} for n, r in rows.items()}}
    rep["stem_swap"] = any(rep["per_stem"][n]["cross_sdr"] > rep["per_stem"][n]["sdr"] for n in names)
    rep["collapse"] = any(not (0.25 < rep["per_stem"][n]["energy_ratio"] < 4) for n in names)
    print(json.dumps(rep, indent=2))
    return rep


if __name__ == "__main__":
    main(*sys.argv[1:3])
