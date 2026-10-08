"""READ-ONLY: what are the stand-alone job results that WebLibrary.entries() still lists, and are they worth keeping?

For every job without an analysis record: preset, creation time, source name (from the asset manifest), length, size, whether its input is (a) a
derived stem of another job, (b) the same audio as a kept analysis' original or a song/ file (sha256), and whether anything references it.
Also reports the stability-v11..v16 / controls-vNN content duplication. Nothing is deleted.   usage: audit-standalone-jobs.py
"""
import hashlib, json, os, re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; DATA = ROOT / "data/separation"
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
gb = lambda n: f"{n / 2**30:.2f} GB"
size_of = lambda p: sum(f.stat().st_size for f in Path(p).rglob("*") if f.is_file()) if Path(p).is_dir() else 0

def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as s:
        for b in iter(lambda: s.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()

records = {p.parent.name: read(p) for p in (DATA / "web").glob("analysis_*/record.json")}
record_text = "\n".join(json.dumps(r) for r in records.values())
kept_original_sha = {sha(DATA / r["original"]) for r in records.values() if r.get("original")}
song_sha = {}
for p in (ROOT / "song").glob("*.mp3"):
    song_sha[sha(p)] = p.name
rows = []
for jf in sorted((DATA / "jobs").glob("job_*/job.json")):
    job = read(jf); folder = jf.parent
    if folder.name in record_text or not (folder / "result/manifest.json").is_file():
        continue
    m = read(folder / "result/manifest.json")
    asset = {}
    try:
        asset = read(DATA / "inputs" / job["asset_id"] / "manifest.json")
    except (OSError, ValueError, KeyError):
        pass
    inp = asset.get("input", {})
    in_sha = inp.get("sha256")
    stems = [s["family"] for s in m.get("stems", [])]
    rows.append({"job": folder.name[-8:], "created": job["created_at_utc"][:16], "preset": job["requested_preset"], "state": job["state"],
                 "source_name": inp.get("original_name"), "seconds": round(m["timeline"]["num_frames"] / 44100, 1), "stems": len(stems),
                 "bytes": size_of(folder) + size_of(DATA / "inputs" / job.get("asset_id", "x")),
                 "same_audio_as_kept_analysis_original": in_sha in kept_original_sha, "same_audio_as_song_file": song_sha.get(in_sha),
                 "asset_id": job.get("asset_id")})
print(f"stand-alone jobs: {len(rows)}  total {gb(sum(r['bytes'] for r in rows))} (job result + its input asset)")
print("by preset:", dict(Counter(r["preset"] for r in rows)))
print("created:", min(r["created"] for r in rows), "..", max(r["created"] for r in rows))
print("source names:", Counter(r["source_name"] for r in rows).most_common(8))
print("input is a kept analysis' original:", sum(r["same_audio_as_kept_analysis_original"] for r in rows), "| input is a song/ file:", sum(1 for r in rows if r["same_audio_as_song_file"]))
print("\n| job | created | preset | source | s | stems | size | song/ match |\n|---|---|---|---|---:|---:|---:|---|")
for r in sorted(rows, key=lambda r: -r["bytes"])[:41]:
    print(f"| {r['job']} | {r['created']} | {r['preset']} | {r['source_name']} | {r['seconds']} | {r['stems']} | {r['bytes'] / 2**20:.0f} MB | {r['same_audio_as_song_file'] or '-'} |")
# which tests / scripts / configs name these ids?
ids = {r["job"] for r in rows}
refs = 0
for pattern in ("separation/tests", "scripts", "docs"):
    for p in (ROOT / pattern).rglob("*"):
        if p.suffix in (".py", ".md", ".json") and p.is_file():
            t = p.read_text(encoding="utf-8", errors="replace")
            if any(("job_" + i) in t or i in t for i in ids if len(i) == 8 and re.search(r"job_[0-9a-f]*" + i, t)):
                refs += 1
print("files in tests/scripts/docs naming any of them:", refs)

# ---- stability / controls version folders
cases = ROOT / "data/ground-truth/cases"
print("\nversioned case folders (physical GB, hash-deduplicated across versions):")
by_hash = defaultdict(list); versions = defaultdict(lambda: [0, 0])
for d in sorted(cases.glob("*-v1[0-9]")):
    for f in d.rglob("*"):
        if f.is_file() and f.stat().st_size >= 1 << 20:
            st = f.stat()
            by_hash[(st.st_size, st.st_dev, st.st_ino)].append((d.name, f))
            versions[d.name][0] += st.st_size; versions[d.name][1] += 1
seen = set(); unique_bytes = 0; hashes = defaultdict(list)
for (size, dev, ino), items in by_hash.items():
    hashes[size].append(items[0])
dup_saving = 0; groups = 0
for size, items in hashes.items():
    if len(items) < 2:
        continue
    byh = defaultdict(list)
    for name, f in items:
        byh[sha(f)].append((name, f))
    for h, g in byh.items():
        if len(g) > 1:
            groups += 1; dup_saving += size * (len(g) - 1)
for name, (b, n) in sorted(versions.items()):
    print(f"  {name:28} {gb(b):>9} {n:5} files")
print(f"content-identical groups across/within version folders: {groups}, saving if one copy each: {gb(dup_saving)}")
# what do the version folders contain besides copies of the same references?
kinds = Counter()
for (size, dev, ino), items in by_hash.items():
    name, f = items[0]
    parts = f.relative_to(cases / name).parts
    kinds[parts[1] if len(parts) > 2 else parts[0]] += size
print("by sub-directory (physical):", {k: gb(v) for k, v in kinds.most_common(8)})
