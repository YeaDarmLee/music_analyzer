"""Data Factory v0 benchmark on FIXTURE assets: spec/render speed, dataloader throughput, cross-process determinism,
storage. Real-asset numbers require DF-0 downloads (sample loading dominates there).
usage: python scripts/df_bench.py [out.json]"""
import json, subprocess, sys, tempfile, time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "src"), str(REPO / "tests")]


def main(out_path):
    from df_fixtures import build_factory
    from data_factory.adapter import DiskCache, SceneDataset
    from data_factory.util import sha256_array
    import torch
    from torch.utils.data import DataLoader

    tmp = Path(tempfile.mkdtemp(prefix="df_bench_"))
    fac, cfgp, _ = build_factory(tmp)
    res = {"note": "FIXTURE assets (procedural tones); not representative of real sample libraries"}
    t = time.perf_counter(); specs = [fac.make_spec(i, "train") for i in range(200)]
    res["spec_generation_ms_per_scene"] = round((time.perf_counter() - t) / 200 * 1000, 2)
    res["spec_json_bytes_mean"] = int(np.mean([len(json.dumps(s.to_dict())) for s in specs]))

    n, rt, aud, store = 20, 0.0, 0.0, []
    for i in range(n):
        s = specs[i]
        t = time.perf_counter(); r = fac.render(s); rt += time.perf_counter() - t
        aud += s.duration_samples / 44100
        store.append(r["mix"].nbytes + sum(r["atomic"][k].nbytes for k in s.active_stems))
    res["full_render"] = {"scenes": n, "seconds_per_scene": round(rt / n, 3), "rtf": round(rt / aud, 3),
                          "mean_scene_seconds": round(aud / n, 2)}
    res["prerender_bytes_per_scene_float32_mean"] = int(np.mean(store))
    t = time.perf_counter()
    for i in range(30):
        fac.render(specs[i], (1.0, 1.0 + 131584 / 44100))
    res["window_render_3s_seconds_per_item"] = round((time.perf_counter() - t) / 30, 3)

    ds = SceneDataset(fac, "train", 64, "2stem_v1", 131584, "lazy")
    thr = {}
    for w in (0, 4, 8):
        dl = DataLoader(ds, batch_size=4, shuffle=False, num_workers=w, persistent_workers=w > 0)
        it = iter(dl); next(it)
        t = time.perf_counter(); k = 0
        for b in it:
            k += b["mix"].shape[0]
            if k >= 40:
                break
        thr[f"workers_{w}"] = round(k / (time.perf_counter() - t), 2)
        del it, dl
    res["dataloader_items_per_second_batch4"] = thr
    cache = DiskCache(tmp / "cache", 2_000_000_000)
    dsc = SceneDataset(fac, "train", 8, "2stem_v1", 131584, "lazy", cache=cache)
    t = time.perf_counter(); [dsc[i] for i in range(8)]; cold = time.perf_counter() - t
    t = time.perf_counter(); [dsc[i] for i in range(8)]; warm = time.perf_counter() - t
    res["cache"] = {"cold_s_per_item": round(cold / 8, 3), "warm_s_per_item": round(warm / 8, 4),
                    "bytes_per_item": int(sum(f.stat().st_size for f in (tmp / "cache").glob("*.npy")) / 8)}

    code = ("import sys,json;sys.path[:0]=[%r,%r];from data_factory.scenes import Factory;"
            "from data_factory.util import sha256_array;f=Factory.from_yaml(%r,%r,__import__('data_factory.assets',fromlist=['x']).load_records(%r));"
            "s=f.make_spec(5,'train');r=f.render(s);print(json.dumps([s.hash(),sha256_array(r['mix'])]))"
            % (str(REPO / "src"), str(REPO / "tests"), str(cfgp), str(tmp), str(tmp / "artifacts_assets")))
    out_sub = json.loads(subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip().splitlines()[-1])
    s5 = fac.make_spec(5, "train")
    here = [s5.hash(), sha256_array(fac.render(s5)["mix"])]
    res["cross_process_determinism"] = {"spec_hash_equal": out_sub[0] == here[0], "audio_hash_equal": out_sub[1] == here[1]}
    res["torch_cuda_available"] = torch.cuda.is_available()
    Path(out_path).write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    if sys.platform == "win32":
        import multiprocessing; multiprocessing.freeze_support()
    main(sys.argv[1] if len(sys.argv) > 1 else "df_bench.json")
