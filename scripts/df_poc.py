"""Data Factory v0 POC on FIXTURE assets (procedurally generated, tests/df_fixtures.py): validates the whole chain
spec -> render -> QC -> manifest policy -> engine runner (train on CUDA) -> checkpoint+provenance -> reload -> inference.
Fixture audio is not representative of real sample libraries; real-asset numbers need DF-0 downloads.
usage: python scripts/df_poc.py [steps]"""
import json, shutil, sys, tempfile, time
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "src"), str(REPO / "tests")]
from df_fixtures import build_factory  # noqa: E402
from data_factory import assets as A  # noqa: E402
from data_factory.scenes import Factory  # noqa: E402
from engine.data.manifest import require_valid  # noqa: E402
from engine.runner import run_experiment  # noqa: E402


def main(steps: int = 12):
    tmp = Path(tempfile.mkdtemp(prefix="df_poc_"))
    fac, df_cfg, records = build_factory(tmp)
    cfg = tmp / "configs"
    for d in ("model", "training", "dataset", "experiment"):
        (cfg / d).mkdir(parents=True)
    shutil.copy(REPO / "configs/model/our_separator_v01.yaml", cfg / "model")
    t = yaml.safe_load((REPO / "configs/training/our_v01_poc.yaml").read_text())
    t.update(max_steps=steps, batch_size=2, grad_accum_steps=2, val_every=6, val_batches=2, checkpoint_every=steps, scheduler=None)
    (cfg / "training/poc.yaml").write_text(yaml.safe_dump(t))
    per = {fac.make_spec(i, s).scene_id: fac.make_spec(i, s).assets for s in ("train", "val") for i in range(4)}
    man = A.build_manifest("df_poc", records, per)
    (cfg / "dataset/df_poc.manifest.json").write_text(json.dumps(man))
    (cfg / "dataset/df_poc.yaml").write_text(yaml.safe_dump({
        "name": "df_poc", "kind": "datafactory_scenes", "plugin": "data_factory.adapter", "usage": "RESEARCH",
        "chunk_seconds": 2.9838, "params": {"manifest": "dataset/df_poc.manifest.json", "factory_config": str(df_cfg),
        "repo_root": str(tmp), "asset_dir": str(tmp / "artifacts_assets"), "target_schema": "2stem_v1", "chunk_samples": 131584, "num_scenes": {"train": 64, "val": 4},
        "cache_dir": None}}))
    (cfg / "experiment/df_poc.yaml").write_text(yaml.safe_dump({
        "name": "df_poc", "output_root": "runs", "model": "model/our_separator_v01.yaml", "training": "training/poc.yaml",
        "dataset": "dataset/df_poc.yaml"}))
    t0 = time.time()
    res = run_experiment(cfg / "experiment/df_poc.yaml", base_dir=tmp)
    log = [json.loads(l) for l in (res["run_dir"] / "metrics.jsonl").read_text().splitlines()]
    out = {"seconds_total": round(time.time() - t0, 1), "steps": steps, "device": res["provenance"].get("model_id"),
           "train_loss": [round(e["loss"], 4) for e in log if e["event"] == "train"],
           "val": [{k: round(v, 3) for k, v in e.items() if k.startswith("val_")} for e in log if e["event"] == "val"],
           "inference": res["inference"], "metrics": res["metrics"], "checkpoint": str(res["checkpoint"]),
           "provenance_keys": sorted(res["provenance"]), "workdir": str(tmp)}
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 12)
