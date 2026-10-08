"""Fill the persistent full-scene cache for a split with several processes (resumable: cached scenes are skipped).
usage: python scripts/df_cache_fill.py <factory_config> <cache_dir> [n_scenes] [procs] [split]
The same cache is used by the training DataLoader (dataset param `scene_cache_dir`); a miss there renders + stores, so the
fill is an optimisation, not a requirement."""
import multiprocessing as mp
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
_ds = None


def _init(cfg, cache_dir, split):
    global _ds
    from data_factory.adapter import SceneCache, SceneDataset
    from data_factory.scenes import Factory
    f = Factory.from_yaml(cfg, REPO)
    _ds = SceneDataset(f, split, 10 ** 9, "2stem_v1", 131584, "lazy", scene_cache=SceneCache(cache_dir))


def _work(i):
    return i, _ds.ensure_cached(i)


def main(cfg, cache_dir, n=None, procs=10, split="train"):
    from data_factory.scenes import Factory
    n = int(n) if n else Factory.from_yaml(cfg, REPO).cfg["dataset_sizes"][split]
    t0, done, hits = time.time(), 0, 0
    with mp.Pool(int(procs), _init, (cfg, cache_dir, split)) as pool:
        for i, hit in pool.imap_unordered(_work, range(n), chunksize=8):
            done += 1
            hits += hit
            if done % 500 == 0 or done == n:
                el = time.time() - t0
                print(f"{done}/{n} already_cached={hits} {done / el:.2f} scenes/s eta {(n - done) / (done / el) / 60:.1f} min", flush=True)
    sz = sum(p.stat().st_size for p in Path(cache_dir).rglob("*.npy"))
    print(f"done {n} scenes in {(time.time() - t0) / 60:.1f} min, cache {sz / 1e9:.1f} GB", flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:])
