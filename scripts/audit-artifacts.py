"""READ-ONLY audit: checkpoints (+ duplicate SHA, registry/production use), benchmark duplicate content, .git size, project-local caches.

Outputs data/audit/artifacts.json. Nothing is modified.
"""
import hashlib, json, os, re, subprocess, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; OUT = ROOT / "data/audit"; OUT.mkdir(exist_ok=True)
sys.path.insert(0, str(ROOT / "separation/src"))
CKPT_EXT = {".ckpt", ".pth", ".pt", ".bin", ".safetensors", ".th", ".onnx"}


def sha256(path, cache={}):
    key = str(path)
    if key not in cache:
        digest = hashlib.sha256()
        with open(path, "rb") as stream:
            for block in iter(lambda: stream.read(1 << 22), b""):
                digest.update(block)
        cache[key] = digest.hexdigest()
    return cache[key]


gb = lambda n: f"{n / 2**30:.2f} GB"
result = {}

# ---------------------------------------------------------------- checkpoints
registry = {}
for reg in (ROOT / "data/separation/models").glob("*/registration.json"):
    try:
        r = json.loads(reg.read_text(encoding="utf-8"))
        registry[(reg.parent / r["checkpoint_filename"]).resolve()] = r["model_id"]
    except (OSError, ValueError, KeyError):
        pass
from music_analyzer import release
production = {}
for preset in ("commercial_2", "commercial_6", "commercial_13"):
    for m in release.model_ids_for(preset):
        production.setdefault(m, []).append(preset)
approvals = json.loads((ROOT / "separation/configs/commercial_approval.json").read_text(encoding="utf-8"))["models"]
checkpoints = []
for dirpath, dirnames, names in os.walk(ROOT):
    if os.sep + ".git" in dirpath or "node_modules" in dirpath:
        continue
    for name in names:
        path = Path(dirpath) / name
        if path.suffix.lower() in CKPT_EXT:
            st = path.stat()
            if st.st_size < 1 << 20:
                continue
            rel = path.relative_to(ROOT).as_posix()
            model_id = registry.get(path.resolve())
            checkpoints.append({"path": rel, "bytes": st.st_size, "nlink": st.st_nlink, "model_id": model_id,
                                "in_venv": rel.startswith(".venv/"), "sha256": sha256(path) if not rel.startswith(".venv/") else None})
by_sha = defaultdict(list)
for c in checkpoints:
    if c["sha256"]:
        by_sha[c["sha256"]].append(c["path"])
for c in checkpoints:
    mid = c["model_id"]
    c["duplicate_of"] = [p for p in by_sha.get(c["sha256"], []) if p != c["path"]] if c["sha256"] else []
    c["registered"] = mid is not None
    c["production_presets"] = production.get(mid, []) if mid else []
    c["approval"] = approvals.get(mid, {}).get("status") if mid else None
result["checkpoints"] = checkpoints
print("checkpoints >= 1MB:", len(checkpoints), "| outside .venv:", sum(1 for c in checkpoints if not c["in_venv"]),
      "| duplicate SHA groups:", sum(1 for v in by_sha.values() if len(v) > 1))

# ---------------------------------------------------------------- benchmark duplicate content
bysize = defaultdict(list)
for sub in ("data/ground-truth", "data/pad-eval"):
    for dirpath, _, names in os.walk(ROOT / sub):
        for name in names:
            path = Path(dirpath) / name
            try:
                st = path.stat()
            except OSError:
                continue
            if st.st_size >= 1 << 20 and path.suffix.lower() in (".wav", ".flac", ".npz", ".npy", ".gz", ".zip"):
                bysize[(st.st_size, st.st_dev, st.st_ino)].append(path)
# group by size, then by hash (hard links of one inode are already one entry)
sizes = defaultdict(list)
for (size, _, _), paths in bysize.items():
    sizes[size].append(paths[0])
groups = defaultdict(list)
for size, paths in sizes.items():
    if len(paths) > 1:
        for p in paths:
            groups[(size, sha256(p))].append(p.relative_to(ROOT).as_posix())
dups = [(k[0], v) for k, v in groups.items() if len(v) > 1]
saving = sum(size * (len(v) - 1) for size, v in dups)
areas = defaultdict(lambda: [0, 0])
for size, v in dups:
    key = "/".join(v[0].split("/")[:3])
    areas[key][0] += size * (len(v) - 1); areas[key][1] += len(v)
result["benchmark_duplicates"] = {"groups": len(dups), "files_in_groups": sum(len(v) for _, v in dups), "dedup_saving_bytes": saving,
                                  "examples": [{"bytes": s, "copies": v[:6]} for s, v in sorted(dups, key=lambda x: -x[0] * len(x[1]))[:15]],
                                  "by_area": {k: {"saving": a[0], "files": a[1]} for k, a in sorted(areas.items(), key=lambda kv: -kv[1][0])[:15]}}
print("benchmark content-duplicate groups:", len(dups), "| potential dedup saving:", gb(saving))

# ---------------------------------------------------------------- .git
git = lambda *a: subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True).stdout
count = git("count-objects", "-vH")
blobs = []
listing = subprocess.run("git rev-list --objects --all", cwd=ROOT, shell=True, capture_output=True, text=True).stdout
batch = subprocess.run(["git", "cat-file", "--batch-check=%(objecttype) %(objectname) %(objectsize) %(rest)"], cwd=ROOT, input=listing, capture_output=True, text=True).stdout
for line in batch.splitlines():
    parts = line.split(" ", 3)
    if parts[0] == "blob":
        blobs.append((int(parts[2]), parts[3] if len(parts) > 3 else ""))
blobs.sort(reverse=True)
git_dir = sum(f.stat().st_size for f in (ROOT / ".git").rglob("*") if f.is_file())
result["git"] = {"dir_bytes": git_dir, "count_objects": count, "lfs": (ROOT / ".git/lfs").exists(), "largest_blobs": [{"bytes": s, "path": p} for s, p in blobs[:10]],
                 "commits": int(git("rev-list", "--count", "--all").strip() or 0)}
print(".git:", gb(git_dir), "| commits", result["git"]["commits"], "| largest blob", (blobs[0][0] / 2**20 if blobs else 0), "MB")

# ---------------------------------------------------------------- caches inside the project
names = {"node_modules", "dist", "build", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".cache", ".npm", ".parcel-cache", "htmlcov"}
caches = defaultdict(lambda: [0, 0])
for dirpath, dirnames, filenames in os.walk(ROOT):
    rel = Path(dirpath).relative_to(ROOT).as_posix()
    for d in list(dirnames):
        if d in names:
            full = Path(dirpath) / d
            size = sum(f.stat().st_size for f in full.rglob("*") if f.is_file())
            where = "venv" if rel.startswith(".venv") else rel.split("/")[0] if rel != "." else "."
            caches[f"{where}:{d}"][0] += size; caches[f"{where}:{d}"][1] += 1
            dirnames.remove(d)
logs = [p for p in ROOT.rglob("*.log") if ".venv" not in p.parts and "node_modules" not in p.parts]
result["caches"] = {k: {"bytes": v[0], "dirs": v[1]} for k, v in caches.items()}
result["logs"] = {"count": len(logs), "bytes": sum(p.stat().st_size for p in logs)}
for k, v in sorted(caches.items(), key=lambda kv: -kv[1][0])[:12]:
    print(f"  cache {k}: {v[0] / 2**20:.1f} MB in {v[1]} dir(s)")
print("logs:", len(logs), "files", f"{result['logs']['bytes'] / 2**20:.1f} MB")
json.dump(result, open(OUT / "artifacts.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
