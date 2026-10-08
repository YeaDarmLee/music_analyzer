"""Data Factory benchmark on the REAL ingested assets (repo config). usage: python scripts/df_bench_real.py out.json"""
import json, subprocess, sys, tempfile, time, warnings
from pathlib import Path
import numpy as np
warnings.filterwarnings("ignore")
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))


def main(out_path):
    import torch
    from torch.utils.data import DataLoader
    from data_factory.adapter import DiskCache, SceneDataset
    from data_factory.qc import qc_scene
    from data_factory.scenes import Factory
    from data_factory.util import sha256_array
    cfgp = REPO / "configs/data_factory/v0.yaml"
    fac = Factory.from_yaml(cfgp, REPO)
    res = {}
    t = time.perf_counter(); specs = [fac.make_spec(i, "train") for i in range(200)]
    res["spec_generation_ms_per_scene"] = round((time.perf_counter() - t) / 200 * 1000, 2)
    res["spec_json_bytes_mean"] = int(np.mean([len(json.dumps(s.to_dict())) for s in specs]))
    n, rt, aud, store, ok = 40, 0.0, 0.0, [], 0
    for i in range(n):
        s = specs[i]
        t = time.perf_counter(); r = fac.render(s); rt += time.perf_counter() - t
        aud += s.duration_samples / 44100
        store.append(r["mix"].nbytes + sum(r["atomic"][k].nbytes for k in s.active_stems))
        ok += qc_scene(r["mix"], r["atomic"], s.active_stems, 44100, s.duration_samples).passed
    res["full_render_cold_cache"] = {"scenes": n, "seconds_per_scene": round(rt / n, 3), "rtf": round(rt / aud, 3),
                                     "mean_scene_seconds": round(aud / n, 2), "qc_pass": f"{ok}/{n}"}
    t = time.perf_counter(); [fac.render(specs[i]) for i in range(20)]; wt = time.perf_counter() - t
    res["full_render_warm_sample_cache_seconds_per_scene"] = round(wt / 20, 3)
    res["prerender_bytes_per_scene_float32_mean"] = int(np.mean(store))
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
    res["dataloader_items_per_second_batch4_full_scene_render"] = thr
    tmp = Path(tempfile.mkdtemp(prefix="df_cache_"))
    dsc = SceneDataset(fac, "train", 8, "2stem_v1", 131584, "lazy", cache=DiskCache(tmp, 2_000_000_000))
    t = time.perf_counter(); [dsc[i] for i in range(8)]; cold = time.perf_counter() - t
    t = time.perf_counter(); [dsc[i] for i in range(8)]; warm = time.perf_counter() - t
    res["disk_cache_full_scene"] = {"cold_s_per_item": round(cold / 8, 3), "warm_s_per_item": round(warm / 8, 4),
                                    "bytes_per_item": int(sum(f.stat().st_size for f in tmp.glob("*.npy")) / 8)}
    code = ("import sys,json,warnings;warnings.filterwarnings('ignore');sys.path.insert(0,%r);from data_factory.scenes import Factory;"
            "from data_factory.util import sha256_array;f=Factory.from_yaml(%r,%r);s=f.make_spec(5,'train');r=f.render(s);"
            "print(json.dumps([s.hash(),sha256_array(r['mix'])]))" % (str(REPO / "src"), str(cfgp), str(REPO)))
    sub = json.loads(subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip().splitlines()[-1])
    s5 = fac.make_spec(5, "train")
    res["cross_process_determinism_real_assets"] = {"spec_hash_equal": sub[0] == s5.hash(), "audio_hash_equal": sub[1] == sha256_array(fac.render(s5)["mix"])}
    res["torch_cuda_available"] = torch.cuda.is_available()
    Path(out_path).write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    import multiprocessing; multiprocessing.freeze_support()
    main(sys.argv[1] if len(sys.argv) > 1 else "df_bench_real.json")
