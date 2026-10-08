"""Full project disk audit (READ-ONLY). Hard links are counted once per inode ("physical") next to the logical size.

usage: disk-audit.py [out.json]    -> top-level / directory / file rankings of everything under the project root (including .git and .venv)
Nothing is deleted or modified.
"""
import json, os, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data/disk-audit.json"
seen = set()                       # (dev, inode) already counted
dir_phys, dir_logical, dir_files = defaultdict(int), defaultdict(int), defaultdict(int)
files = []                         # (physical bytes, logical bytes, nlink, path)
for dirpath, dirnames, names in os.walk(ROOT):
    for name in names:
        path = os.path.join(dirpath, name)
        try:
            st = os.lstat(path)
        except OSError:
            continue
        key = (st.st_dev, st.st_ino)
        first = key not in seen and st.st_nlink >= 1
        seen.add(key)
        physical = st.st_size if first else 0
        rel = os.path.relpath(path, ROOT).replace("\\", "/")
        parts = rel.split("/")
        for depth in range(0, min(len(parts) - 1, 4) + 1):
            d = "/".join(parts[:depth]) or "."
            dir_phys[d] += physical; dir_logical[d] += st.st_size; dir_files[d] += 1
        if st.st_size >= 100 * 2**20:
            files.append((physical, st.st_size, st.st_nlink, rel))
total_phys = dir_phys["."]; total_logical = dir_logical["."]
top = sorted(((d, dir_phys[d], dir_logical[d], dir_files[d]) for d in dir_phys if "/" not in d and d != "."), key=lambda x: -x[1])
dirs = sorted(((d, dir_phys[d], dir_logical[d], dir_files[d]) for d in dir_phys if d != "."), key=lambda x: -x[1])
files.sort(key=lambda x: -x[1])
gb = lambda n: f"{n / 2**30:,.2f} GB"
print(f"TOTAL physical {gb(total_phys)}  logical {gb(total_logical)}  files {dir_files['.']:,}")
print("\nTOP-LEVEL (physical / logical / files)")
for d, p, l, n in top[:25]:
    print(f"  {gb(p):>10} {gb(l):>10} {n:>8,}  {d}")
print("\nDIRECTORIES >= 1 GB physical:", sum(1 for d in dirs if d[1] >= 2**30))
print("FILES >= 500 MB:", sum(1 for f in files if f[1] >= 500 * 2**20))
out.write_text(json.dumps({"total_physical": total_phys, "total_logical": total_logical, "files": dir_files["."],
                           "top_level": top, "directories": dirs[:300], "big_files": files[:300]}, ensure_ascii=False, indent=1), encoding="utf-8")
