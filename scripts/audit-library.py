"""READ-ONLY audit of the application library (data/separation): analyses, unlinked jobs/inputs, reset backup.

Outputs data/audit/library.json. Nothing is modified; the auth DB is only read (ownership rows).
Classification evidence (never the name alone):
  DEMO         the rights-confirmed AI-generated sample song (name matches the sample manifest title)
  BENCHMARK    older iterations of the same source analysed again with another pipeline version, or analyses derived from another analysis
  MANUAL_TEST  source is a file of the developer's local song/ collection (commercial tracks, dev accounts, development window)
  REAL_USER    owned by an account with evidence of a real external user - none can be proven here
  UNKNOWN      anything else
"""
import json, os, re, sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import psutil

ROOT = Path(__file__).resolve().parents[1]; DATA = ROOT / "data/separation"; OUT = ROOT / "data/audit"; OUT.mkdir(exist_ok=True)
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
size_of = lambda p: sum(f.stat().st_size for f in Path(p).rglob("*") if f.is_file()) if Path(p).is_dir() else (Path(p).stat().st_size if Path(p).exists() else 0)
norm = lambda s: re.sub(r"[\s\W_]+", "", str(s)).lower()
songs = {norm(p.stem): p.name for p in (ROOT / "song").glob("*.mp3")}
try:
    owners_rows = read(ROOT / "data/owners-snapshot.json")
except OSError:
    owners_rows = []
owner_of = defaultdict(list)
for row in owners_rows:
    owner_of[row["analysis_id"]].append(row["user_id"][:6])
users = sorted({u for v in owner_of.values() for u in v})

records = {}
for path in sorted((DATA / "web").glob("analysis_*/record.json")):
    records[path.parent.name] = read(path)
names = Counter(r.get("name") for r in records.values())
by_name = defaultdict(list)
for i, r in records.items():
    by_name[r.get("name")].append((str(r.get("created")), i))
newest = {name: max(v)[1] for name, v in by_name.items()}
DEMO_TITLES = {norm("오늘을 채워 가")}
rows = []
for i, r in records.items():
    folder = DATA / "web" / i
    finals = [f for f in (folder / "final").glob("*") if f.is_file()] if (folder / "final").is_dir() else []
    final_bytes = sum(f.stat().st_size for f in finals)
    original = folder / "original.wav"
    original_bytes = original.stat().st_size if original.exists() else 0
    stats = [f.stat() for f in [*finals, original] if f.exists()]
    name = r.get("name") or ""
    base_name = re.sub(r"\s*·.*$", "", name)
    import difflib
    key = norm(base_name)
    in_song = songs.get(key) or next((songs[k] for k in songs if len(k) >= 6 and len(key) >= 6 and (k in key or key in k)), None)   # exact first; substrings only for titles of 6+ characters
    if not in_song and key:   # titles written differently (e.g. "millsage - 기사개전 (起死開戦)" vs song/millsage-(起死開戦.mp3)
        best = max(songs, key=lambda k: difflib.SequenceMatcher(None, k, key).ratio())
        in_song = songs[best] if difflib.SequenceMatcher(None, best, key).ratio() >= .6 else None
    derived = bool(r.get("parent_analysis_id")) or "보완" in name or "리드/코러스" in name
    evidence, kind = [], "UNKNOWN"
    if norm(base_name) in DEMO_TITLES:
        kind = "DEMO"; evidence.append("title is the AI-generated sample song (rights confirmed by the user)")
    elif derived:
        kind = "BENCHMARK"; evidence.append("derived from another analysis (parent_analysis_id / '보완' / '리드/코러스' in the name)")
    elif in_song and newest.get(name) != i:
        kind = "BENCHMARK"; evidence.append(f"older iteration: the same source '{in_song}' was analysed again later with another pipeline version")
    elif in_song:
        kind = "MANUAL_TEST"; evidence.append(f"source matches song/{in_song} (developer's local collection of commercial tracks)")
    else:
        evidence.append("source is not in song/ and not the demo track")
    rows.append({"id": i, "created": r.get("created"), "preset": r.get("model"), "version": r.get("separation_version"), "state": r.get("state"),
                 "kind_of_record": r.get("kind"), "name": name, "same_name_count": names[name], "owners": owner_of.get(i, []),
                 "in_library_for_accounts": bool(owner_of.get(i)), "final_bytes": final_bytes, "original_bytes": original_bytes,
                 "folder_bytes": size_of(folder), "record_mtime": datetime.fromtimestamp((folder / "record.json").stat().st_mtime, timezone.utc).isoformat()[:19],
                 "max_atime": datetime.fromtimestamp(max((s.st_atime for s in stats), default=0), timezone.utc).isoformat()[:19] if stats else None,
                 "storage": (r.get("storage") or {}).get("mode"), "classification": kind, "evidence": evidence,
                 "source_file": in_song, "script_trace": derived})

# ---- jobs / inputs not tied to an analysis
all_record_text = "\n".join(json.dumps(r) for r in records.values())
pipeline_text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in (DATA / "pipelines").glob("*/manifest.json")) if (DATA / "pipelines").is_dir() else ""
referenced_jobs = set(re.findall(r"job_[0-9a-f]{32}", all_record_text + pipeline_text))
referenced_assets = set(re.findall(r"asset_[0-9a-f]{32}", all_record_text + pipeline_text))
jobs, job_assets = [], defaultdict(set)
for folder in sorted((DATA / "jobs").glob("job_*")):
    try:
        job = read(folder / "job.json")
    except (OSError, ValueError):
        job = {}
    has_result = (folder / "result" / "manifest.json").is_file()
    owner = job.get("owner") or {}
    alive = False
    try:
        alive = bool(owner.get("pid")) and psutil.pid_exists(owner["pid"]) and abs(psutil.Process(owner["pid"]).create_time() - owner.get("create_time", 0)) < 2
    except psutil.Error:
        pass
    linked = folder.name in referenced_jobs
    state = job.get("state", "NO_JOB_JSON")
    if alive and state not in ("SUCCEEDED", "FAILED", "CANCELLED"):
        cls = "ACTIVE"
    elif linked:
        cls = "LINKED_TO_ANALYSIS"
    elif has_result and state == "SUCCEEDED":
        cls = "LIBRARY_RECORD"      # shown by WebLibrary.entries() as a stand-alone result
    elif state in ("FAILED", "CANCELLED"):
        cls = "FAILED_JOB"
    else:
        cls = "ORPHAN"
    if job.get("asset_id"):
        job_assets[job["asset_id"]].add((folder.name, cls))
    jobs.append({"id": folder.name, "state": state, "preset": job.get("requested_preset"), "created": job.get("created_at_utc"), "bytes": size_of(folder),
                 "has_result": has_result, "class": cls, "asset": job.get("asset_id")})
assets = []
for folder in sorted((DATA / "inputs").glob("asset_*")):
    uses = job_assets.get(folder.name, set())
    classes = {c for _, c in uses}
    if folder.name in referenced_assets:
        cls = "LINKED_TO_ANALYSIS"
    elif "ACTIVE" in classes:
        cls = "ACTIVE"
    elif "LIBRARY_RECORD" in classes:
        cls = "LIBRARY_RECORD"
    elif classes & {"FAILED_JOB"}:
        cls = "FAILED_JOB"
    elif classes:
        cls = "LINKED_TO_ANALYSIS"   # used only by jobs that belong to an analysis trail
    else:
        cls = "ORPHAN"
    original_name = None
    try:
        original_name = read(folder / "manifest.json")["input"]["original_name"]
    except (OSError, ValueError, KeyError):
        pass
    assets.append({"id": folder.name, "bytes": size_of(folder), "class": cls, "uses": sorted(u for u, _ in uses), "original_name": original_name})

# ---- reset backup vs current library
backup = {}
for b in (ROOT / "data/reset-backups").glob("*"):
    ids = {p.parent.name for p in (b / "web").glob("analysis_*/record.json")}
    names_b = {}
    for p in (b / "web").glob("analysis_*/record.json"):
        try:
            names_b[p.parent.name] = read(p).get("name")
        except (OSError, ValueError):
            pass
    backup[b.name] = {"bytes": size_of(b), "analysis_ids": len(ids), "ids_also_in_current_library": len(ids & set(records)),
                      "jobs": len(list((b / "jobs").glob("job_*"))) if (b / "jobs").is_dir() else 0,
                      "inputs": len(list((b / "inputs").glob("asset_*"))) if (b / "inputs").is_dir() else 0,
                      "substems": len(list((b / "substems").glob("*"))) if (b / "substems").is_dir() else 0,
                      "names": sorted({str(n) for n in names_b.values()})[:20],
                      "names_missing_from_current": sorted({str(n) for n in names_b.values()} - {r.get("name") for r in records.values()})}
json.dump({"users_seen": users, "analyses": rows, "jobs": jobs, "assets": assets, "reset_backups": backup}, open(OUT / "library.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
gb = lambda n: f"{n / 2**30:.2f} GB"
print("analyses:", len(rows), "| kinds:", dict(Counter(r["classification"] for r in rows)), "| total", gb(sum(r["folder_bytes"] for r in rows)))
for k in ("DEMO", "BENCHMARK", "MANUAL_TEST", "UNKNOWN", "REAL_USER"):
    print(f"  {k:12} {sum(1 for r in rows if r['classification'] == k):3}  {gb(sum(r['folder_bytes'] for r in rows if r['classification'] == k))}")
print("jobs:", dict(Counter(j["class"] for j in jobs)), {c: gb(sum(j["bytes"] for j in jobs if j["class"] == c)) for c in {j["class"] for j in jobs}})
print("assets:", dict(Counter(a["class"] for a in assets)), {c: gb(sum(a["bytes"] for a in assets if a["class"] == c)) for c in {a["class"] for a in assets}})
print("reset backups:", json.dumps({k: {x: y for x, y in v.items() if x != "names"} for k, v in backup.items()}, ensure_ascii=False))
