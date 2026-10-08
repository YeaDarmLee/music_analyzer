"""Approved disk cleanup (see docs/FULL_DISK_AUDIT_KO.md). Default is a PLAN (no deletion); --apply performs it.

Stages (each re-verifies its references right before deleting):
  1 safe      orphan input assets (no record / pipeline / job.json / prepared.json / active job names them), __pycache__ and .pytest_cache,
              old smoke output (never data/separation/runtime, logs, frontend/dist or node_modules)
  2 analyses  MANUAL_TEST + BENCHMARK analyses through the normal path: WebLibrary.delete() + AuthStore.release() (DB ownership row)
  3 tools     tools/AudioSep and tools/wesep-reference after a reference check (audiosep-env stays: clapsep-env uses it); provenance is written first
  4 backup    data/reset-backups after copying its small JSON metadata into docs/legacy-backups/
KEEP (not touched): DEMO + UNKNOWN analyses, CLAPSep stack, UNKNOWN-license checkpoints, the 41 stand-alone jobs.
usage: apply-disk-cleanup.py [--apply] [--stage safe,analyses,tools,backup]
"""
import argparse, ast, json, os, re, shutil, subprocess, sys, time
from collections import Counter
from pathlib import Path
import psutil

ROOT = Path(__file__).resolve().parents[1]; DATA = ROOT / "data/separation"; AUDIT = ROOT / "data/audit"
sys.path.insert(0, str(ROOT / "separation/src"))
EXPECTED = {"MANUAL_TEST": 23, "BENCHMARK": 23, "DEMO": 2, "UNKNOWN": 2, "REAL_USER": 0}
ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--stage", default="safe,analyses,tools,backup")
args = ap.parse_args(); stages = args.stage.split(",")
gb = lambda n: f"{n / 2**30:,.2f} GB"
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
size_of = lambda p: sum(f.stat().st_size for f in Path(p).rglob("*") if f.is_file()) if Path(p).is_dir() else (Path(p).stat().st_size if Path(p).exists() else 0)
run = lambda *cmd: subprocess.run(cmd, cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT / "separation/src"), "PYTHONUTF8": "1"}, capture_output=True, text=True)


def refresh():
    """Recompute ownership snapshot (DB) and the library classification from the live data."""
    out = run(sys.executable, "-c", "import runpy; runpy.run_path(r'" + str(ROOT / 'data/audit/_owners.py') + "')")
    if out.returncode:
        sys.exit("owner snapshot failed: " + out.stderr[-300:])
    out = run(sys.executable, str(ROOT / "scripts/audit-library.py"))
    if out.returncode:
        sys.exit("library audit failed: " + out.stderr[-300:])
    return read(AUDIT / "library.json"), read(ROOT / "data/owners-snapshot.json")


(AUDIT / "_owners.py").write_text('''import json
from music_analyzer.auth import AuthStore
rows = AuthStore().query("SELECT analysis_id, user_id FROM analysis_owners")
json.dump([{"analysis_id": r["analysis_id"], "user_id": r["user_id"]} for r in rows], open(r"C:\\workspace\\music_analyzer\\data\\owners-snapshot.json", "w"))
''', encoding="utf-8")
lib, owners = refresh()
records = {p.parent.name: read(p) for p in (DATA / "web").glob("analysis_*/record.json")}
by_class = {}
for a in lib["analyses"]:
    by_class.setdefault(a["classification"], []).append(a)
print("=== analyses by category (ids are the last 8 hex digits) ===")
for k in ("MANUAL_TEST", "BENCHMARK", "DEMO", "UNKNOWN", "REAL_USER"):
    items = by_class.get(k, [])
    print(f"{k}: {len(items)}  states={dict(Counter(a['state'] for a in items))}  {gb(sum(a['folder_bytes'] for a in items))}")
    for a in sorted(items, key=lambda a: a["created"]):
        print(f"   {a['id'][-8:]} {a['created'][:16]} {a['preset']:9} {a['state']:9} owners={','.join(a['owners']) or '-':7} {a['name'][:50]}")
delete_ids, keep_ids = [], []
if "analyses" in stages:
    # ---- assertions: report numbers == real DB / filesystem numbers
    assert len(records) == len(lib["analyses"]) == 50, (len(records), len(lib["analyses"]))
    for k, n in EXPECTED.items():
        assert len(by_class.get(k, [])) == n, f"{k}: expected {n}, found {len(by_class.get(k, []))}"
    owner_ids = {o["analysis_id"] for o in owners}
    assert owner_ids <= set(records), f"DB owner rows without a record: {sorted(owner_ids - set(records))[:3]}"
    unowned = set(records) - owner_ids
    assert {records[i]["state"] for i in unowned} == {"FAILED"} and len(unowned) == 1, "the only analysis without an owner must be the FAILED one"
    assert len(owner_ids) == 49
    delete_ids = [a["id"] for k in ("MANUAL_TEST", "BENCHMARK") for a in by_class[k]]
    keep_ids = [a["id"] for k in ("DEMO", "UNKNOWN") for a in by_class[k]]
    assert len(delete_ids) == 46 and len(keep_ids) == 4 and not set(delete_ids) & set(keep_ids)
    assert sum(1 for i in delete_ids if records[i]["state"] == "SUCCEEDED") == 45 and sum(1 for i in delete_ids if records[i]["state"] == "FAILED") == 1
    print(f"\nASSERT OK: 50 records = 46 to delete (45 SUCCEEDED + 1 FAILED, 45 with a DB owner row) + 4 kept; DB owner rows 49")
    print("note: the earlier 'REVIEW 47' = DEMO 2 + MANUAL_TEST 23 + SUCCEEDED BENCHMARK 22; the FAILED BENCHMARK record is counted in the SAFE bucket there.\n")

before = {"project": None}
disk_before = run(sys.executable, str(ROOT / "scripts/disk-audit.py"), str(ROOT / "data/disk-before.json"))
before_json = read(ROOT / "data/disk-before.json")
free_before = shutil.disk_usage(ROOT).free
report = {"before": {"project_bytes": before_json["total_physical"], "free_bytes": free_before,
                     "top": {d: p for d, p, _, _ in before_json["top_level"]}}}
print(f"BEFORE: project {gb(before_json['total_physical'])}, free {gb(free_before)}")


def references():
    """ids named anywhere that keeps an asset/job alive"""
    texts = [p.read_text(encoding="utf-8", errors="replace") for p in (DATA / "web").glob("analysis_*/record.json")]
    texts += [p.read_text(encoding="utf-8", errors="replace") for p in (DATA / "pipelines").glob("*/manifest.json")]
    texts += [p.read_text(encoding="utf-8", errors="replace") for p in (DATA / "jobs").glob("job_*/job.json")]
    for name in ("prepared.json", "case.json", "run.json"):   # source dependencies of benchmark cases
        texts += [p.read_text(encoding="utf-8", errors="replace") for p in (ROOT / "data").rglob(name) if "separation" not in p.parts]
    ids = set()
    for t in texts:
        ids |= set(re.findall(r"(?:job|asset)_[0-9a-f]{32}", t))
    active = set()
    for jf in (DATA / "jobs").glob("job_*/job.json"):
        j = read(jf)
        owner = j.get("owner") or {}
        try:
            alive = owner.get("pid") and psutil.pid_exists(owner["pid"]) and abs(psutil.Process(owner["pid"]).create_time() - owner.get("create_time", 0)) < 2
        except psutil.Error:
            alive = False
        if j.get("state") not in ("SUCCEEDED", "FAILED", "CANCELLED") and alive:
            active.add(jf.parent.name); ids.add(j.get("asset_id"))
    busy = [i for i, r in ((p.parent.name, read(p)) for p in (DATA / "web").glob("analysis_*/record.json")) if r.get("state") in ("QUEUED", "RUNNING")]
    return ids, active, busy


removed = {"files": 0, "bytes": 0}
def rm(path):
    path = Path(path)
    if not path.exists():
        return 0
    n = size_of(path); files = sum(1 for f in path.rglob("*") if f.is_file()) if path.is_dir() else 1
    if args.apply:
        def writable(function, target, error):   # git packs are read-only on Windows
            os.chmod(target, 0o700); function(target)
        shutil.rmtree(path, onexc=writable) if path.is_dir() else path.unlink()
        removed["files"] += files; removed["bytes"] += n
    return n


# =============================================================== 1 safe
if "safe" in stages:
    refs, active, busy = references()
    assert not active and not busy, f"active work: {active} {busy}"
    orphans = [a for a in lib["assets"] if a["class"] == "ORPHAN"]
    todo, skipped = [], []
    for a in orphans:
        (skipped if a["id"] in refs else todo).append(a)
    total = sum(a["bytes"] for a in todo)
    print(f"\n[1 safe] orphan assets: {len(orphans)} planned, {len(skipped)} now referenced (kept), {len(todo)} to delete = {gb(total)}")
    for a in todo:
        rm(DATA / "inputs" / a["id"])
    freed_cache = 0
    for pattern in ("__pycache__", ".pytest_cache"):
        for d in ROOT.rglob(pattern):
            if d.is_dir() and "node_modules" not in d.parts:
                freed_cache += rm(d)
    smoke = sum(rm(DATA / n) for n in ("smoke", "s2-validation", "s3-validation"))
    print(f"[1 safe] caches {gb(freed_cache)} (pycache/.pytest_cache; frontend/dist and node_modules kept: the app serves/builds from them), old smoke output {gb(smoke)}; data/separation/runtime untouched")
    report["safe"] = {"orphan_assets_deleted": len(todo), "orphan_assets_kept_now_referenced": len(skipped), "orphan_bytes": total, "cache_bytes": freed_cache, "smoke_bytes": smoke}

# =============================================================== 2 analyses
if "analyses" in stages:
    from music_analyzer.auth import AuthStore
    from music_analyzer.web_server import WebLibrary
    store = AuthStore()
    library = WebLibrary(DATA) if args.apply else None   # its constructor runs the startup sweep, so a plan run must not create it
    done, freed = [], 0
    try:
        print(f"\n[2 analyses] {len(delete_ids)} deletions through WebLibrary.delete + AuthStore.release")
        for identifier in delete_ids:
            row = records[identifier]
            assert identifier not in keep_ids
            before_size = size_of(DATA / "web" / identifier)
            if args.apply:
                try:
                    library.delete(identifier)
                except FileNotFoundError:
                    pass
                store.release(identifier)
                assert not (DATA / "web" / identifier).exists(), identifier
                assert not store.query("SELECT 1 FROM analysis_owners WHERE analysis_id=%s", (identifier,)), "DB ownership row left"
            done.append(identifier); freed += before_size
            print(f"   {'deleted' if args.apply else 'would delete'} {identifier[-8:]} {row['state']:9} {before_size / 2**30:5.2f} GB {row['name'][:40]}")
        if args.apply:
            left = {p.parent.name for p in (DATA / "web").glob("analysis_*/record.json")}
            assert left == set(keep_ids), f"remaining analyses differ from the KEEP list: {sorted(left)}"
            rows = {o["analysis_id"] for o in store.query("SELECT analysis_id FROM analysis_owners")}
            assert rows <= left, "DB owner rows for analyses that no longer exist"
            print(f"[2 analyses] remaining records = {len(left)} (DEMO 2 + UNKNOWN 2), DB owner rows = {len(rows)}, all consistent")
    finally:
        if library is not None:
            library.executor.shutdown(wait=True)
    report["analyses"] = {"deleted": len(done), "analysis_folder_bytes": freed}

# =============================================================== 3 tools
if "tools" in stages:
    tools = DATA / "tools"
    targets = [tools / "AudioSep", tools / "wesep-reference"]
    # audiosep-env is NOT a target: clapsep-env (final_11 baseline cymbal path) takes its packages from it through music_analyzer_base.pth
    pth = (tools / "clapsep-env/Lib/site-packages/music_analyzer_base.pth").read_text(encoding="utf-8")
    assert "audiosep-env" in pth, "unexpected: clapsep-env no longer uses audiosep-env"
    for env_pth in list((tools / "clapsep-env/Lib/site-packages").glob("*.pth")) + list((tools / "audiosep-env/Lib/site-packages").glob("music_analyzer_base.pth")):
        text = env_pth.read_text(encoding="utf-8", errors="ignore")
        assert not re.search(r"tools[\/]+(AudioSep|wesep-reference)", text), f"{env_pth} points into a deletion target"
    # path-level check: what actually opens tools/AudioSep or tools/wesep-reference?
    pattern = re.compile(r"tools[\/]+(AudioSep|wesep-reference)|wesep-reference")
    src_hits = {f.relative_to(ROOT).as_posix(): [i + 1 for i, l in enumerate(f.read_text(encoding="utf-8").splitlines()) if pattern.search(l)]
                for f in list((ROOT / "separation/src").rglob("*.py")) + list((ROOT / "separation/tests").rglob("*.py")) + list((ROOT / "separation/configs").rglob("*.json"))}
    src_hits = {k: v for k, v in src_hits.items() if v}
    script_hits = sorted(f.name for f in (ROOT / "scripts").glob("*.py") if pattern.search(f.read_text(encoding="utf-8")) and f.name not in ("apply-disk-cleanup.py", "audit-doc.py", "audit-report.py", "audit-artifacts.py"))
    print(f"\n[3 tools] path references in src/tests/configs: {src_hits}; scripts that (re)create or use them: {script_hits}")
    assert set(src_hits) <= {"separation/src/music_analyzer/audiosep_experiment.py"}, f"runtime/test dependency: {src_hits}"
    for rel, lines in src_hits.items():   # the only allowed hit is the CLI default of the AudioSep experiment (--repo), not reachable from a pipeline
        text = (ROOT / rel).read_text(encoding="utf-8").splitlines()
        assert all("add_argument(\"--repo\"" in text[n - 1] for n in lines), f"{rel}: {lines}"
    # the CLAPSep environment must still import after the deletion: check before, repeat after (post-integrity)
    probe = subprocess.run([str(tools / "clapsep-env/Scripts/python.exe"), "-c", "import torch, laion_clap, music_analyzer.clapsep_experiment; print('ok')"], capture_output=True, text=True,
                           env={**os.environ, "PYTHONPATH": str(ROOT / "separation/src")})
    assert probe.stdout.strip().endswith("ok"), "clapsep-env does not import: " + probe.stderr[-300:]
    print("[3 tools] clapsep-env imports torch + laion_clap + clapsep_experiment (before deletion)")
    registry_models = [p.stem for p in (ROOT / "separation/configs/models").glob("*.json")]
    prov = {"retired_on": time.strftime("%Y-%m-%d"), "reason": "research-only tools: no production, commercial, final_11-baseline or test dependency (path references and .pth files checked)",
            "kept_on_purpose": "tools/audiosep-env (0.28 GB): clapsep-env loads its packages through music_analyzer_base.pth",
            "audiosep": {"repository": "https://github.com/Audio-AGI/AudioSep.git", "commit": subprocess.run(["git", "-C", str(tools / "AudioSep"), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip(),
                         "registry": "separation/configs/models/audiosep_base.json", "scripts_that_used_it": script_hits,
                         "checkpoints": []},
            "wesep_reference": {"prepare_script": "data/separation/tools/prepare-wesep-reference.py (kept)", "checkpoints": []}}
    art = read(AUDIT / "artifacts.json")
    for c in art["checkpoints"]:
        if "tools/AudioSep/" in c["path"]:
            prov["audiosep"]["checkpoints"].append({"file": c["path"].split("tools/")[1], "bytes": c["bytes"], "sha256": c["sha256"]})
        if "tools/wesep-reference/" in c["path"]:
            prov["wesep_reference"]["checkpoints"].append({"file": c["path"].split("tools/")[1], "bytes": c["bytes"], "sha256": c["sha256"]})
    if (tools / "wesep-reference").is_dir():
        for f in (tools / "wesep-reference").rglob("*"):
            if f.is_file() and f.suffix in (".gz", ".zip") and f.stat().st_size > 1 << 20:
                import hashlib
                h = hashlib.sha256()
                with open(f, "rb") as s:
                    for b in iter(lambda: s.read(1 << 22), b""):
                        h.update(b)
                prov["wesep_reference"]["checkpoints"].append({"file": f.relative_to(tools).as_posix(), "bytes": f.stat().st_size, "sha256": h.hexdigest()})
    for lock in (tools / "audiosep-environment-lock.txt",):
        if lock.exists():
            prov["audiosep"]["environment_lock"] = "data/separation/tools/audiosep-environment-lock.txt (kept)"
    total = sum(size_of(t) for t in targets)
    print(f"[3 tools] to delete: {[t.name for t in targets]} = {gb(total)}; provenance -> docs/RETIRED_TOOLS_PROVENANCE.json")
    if args.apply:
        (ROOT / "docs/RETIRED_TOOLS_PROVENANCE.json").write_text(json.dumps(prov, ensure_ascii=False, indent=1), encoding="utf-8")
        for t in targets:
            rm(t)
    if args.apply:
        probe = subprocess.run([str(tools / "clapsep-env/Scripts/python.exe"), "-c", "import torch, laion_clap, music_analyzer.clapsep_experiment; print('ok')"], capture_output=True, text=True,
                               env={**os.environ, "PYTHONPATH": str(ROOT / "separation/src")})
        assert probe.stdout.strip().endswith("ok"), "clapsep-env BROKEN after deletion: " + probe.stderr[-300:]
        print("[3 tools] clapsep-env still imports torch + laion_clap + clapsep_experiment (after deletion)")
    report["tools"] = {"bytes": total, "deleted": [t.name for t in targets]}

# =============================================================== 4 reset-backups
if "backup" in stages:
    backups = ROOT / "data/reset-backups"
    keep_small = []
    for f in backups.rglob("*"):
        if f.is_file() and f.suffix.lower() in (".json", ".txt") and f.stat().st_size < 1 << 20 and "environment.freeze" not in f.name:
            keep_small.append(f)
    meta_bytes = sum(f.stat().st_size for f in keep_small)
    total = size_of(backups)
    print(f"\n[4 backup] {backups.name}: {gb(total)}; small metadata kept: {len(keep_small)} files, {meta_bytes / 1024:.0f} KB -> docs/legacy-backups/")
    if args.apply:
        for f in keep_small:
            target = ROOT / "docs/legacy-backups" / f.relative_to(backups)
            target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(f, target)
        rm(backups)
    report["backup"] = {"bytes": total, "metadata_files": len(keep_small), "metadata_kb": round(meta_bytes / 1024)}

if args.apply:
    run(sys.executable, str(ROOT / "scripts/disk-audit.py"), str(ROOT / "data/disk-after.json"))
    after = read(ROOT / "data/disk-after.json")
    report["after"] = {"project_bytes": after["total_physical"], "free_bytes": shutil.disk_usage(ROOT).free, "top": {d: p for d, p, _, _ in after["top_level"]},
                       "directories": after["directories"][:20]}
    report["removed_files_counted_by_script"] = removed["files"]; report["removed_bytes_counted_by_script"] = removed["bytes"]
    (AUDIT / "cleanup-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nAFTER: project {gb(after['total_physical'])} (was {gb(before_json['total_physical'])}), free {gb(shutil.disk_usage(ROOT).free)}; files removed (script count) {removed['files']:,}")
else:
    print("\nPLAN ONLY - nothing deleted. Re-run with --apply.")
