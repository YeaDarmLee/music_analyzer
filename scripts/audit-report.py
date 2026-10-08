"""READ-ONLY: classify every file of the project into A-I and SAFE/REVIEW/KEEP/UNKNOWN, using data/audit/*.json from the other audit scripts.

Prints markdown tables and writes data/audit/classified.json. Physical bytes: a hard-linked inode is counted once.
"""
import json, os, re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; A = ROOT / "data/audit"
lib = json.loads((A / "library.json").read_text(encoding="utf-8")); art = json.loads((A / "artifacts.json").read_text(encoding="utf-8"))
analysis_class = {a["id"]: a["classification"] for a in lib["analyses"]}
analysis_state = {a["id"]: a["state"] for a in lib["analyses"]}
job_class = {j["id"]: j["class"] for j in lib["jobs"]}
asset_class = {a["id"]: a["class"] for a in lib["assets"]}
failed_ids = {a["id"] for a in lib["analyses"] if a["state"] != "SUCCEEDED"}
records = {p.parent.name: json.loads(p.read_text(encoding="utf-8")) for p in (ROOT / "data/separation/web").glob("analysis_*/record.json")}
failed_jobs = {j for i in failed_ids for j in records[i].get("job_ids", [])}
failed_assets = set()
for j in failed_jobs:
    try:
        failed_assets.add(json.loads((ROOT / "data/separation/jobs" / j / "job.json").read_text(encoding="utf-8"))["asset_id"])
    except (OSError, ValueError, KeyError):
        pass
production_models = {c["path"].split("/")[3] for c in art["checkpoints"] if c["production_presets"]}
derived_sources = {"mega53_3head"}   # holds official-53.ckpt, the source every pruned production head was derived from


def classify(rel):
    """-> (category A-I, risk SAFE/REVIEW/KEEP/UNKNOWN, label)"""
    p = rel.split("/")
    if p[0] == ".git":
        return "A", "KEEP", ".git"
    if p[0] == ".venv":
        return ("F", "SAFE", ".venv __pycache__") if "__pycache__" in p else ("A", "KEEP", ".venv (runtime; rebuildable from requirements but required to run)")
    if p[0] in ("separation", "scripts", "docs", "frontend", ".github") or p[0].startswith("."):
        if "node_modules" in p or p[:2] == ["frontend", "dist"] or "__pycache__" in p or ".pytest_cache" in p:
            return "F", "SAFE", "build / dependency caches"
        return "A", "KEEP", "source, config, docs, license evidence, frontend"
    if p[0] == "song":
        return "E", "REVIEW", "song/ (developer's local commercial mp3 collection, not tracked)"
    if p[0] != "data":
        return "I", "UNKNOWN", rel.split("/")[0]
    if len(p) == 2:
        return "F", "SAFE", "logs / markers" if p[1].endswith((".log", ".done", ".txt")) else "I"
    top = p[1]
    if top == "separation":
        sub = p[2] if len(p) > 2 else ""
        if sub == "models":
            m = p[3] if len(p) > 3 else ""
            if m in production_models:
                return "A", "KEEP", "production checkpoints (APPROVED)"
            if m in derived_sources:
                return "E", "REVIEW", "official-53 source checkpoint + 3-head experiment (provenance for pruned heads)"
            return "E", "REVIEW", "non-production weights (UNKNOWN license / experiments / baseline final_11)"
        if sub == "tools":
            t = p[3] if len(p) > 3 else ""
            if t in ("CLAPSep", "CLAPSepInference", "clapsep-env"):
                return "E", "REVIEW", "CLAPSep stack (needed only by the final_11 BASELINE cymbal path)"
            if t in ("AudioSep", "audiosep-env", "wesep-reference", "prepare-wesep-reference.py", "audiosep-environment-lock.txt", "grouped-smoke.wav", "clapsep-run.log"):
                return "E", "REVIEW", "AudioSep / wesep research tools (no production or baseline path)"
            return "E", "REVIEW", "tools"
        if sub == "web":
            if "__pycache__" in p:
                return "F", "SAFE", "pycache"
            aid = p[3] if len(p) > 3 else ""
            if aid in failed_ids:
                return "H", "SAFE", "FAILED analysis record (no deliverable)"
            k = analysis_class.get(aid)
            if k in ("MANUAL_TEST", "BENCHMARK", "DEMO"):
                return "B", "REVIEW", f"library analysis - {k} (visible in the dev accounts' library)"
            if k == "UNKNOWN":
                return "I", "UNKNOWN", "library analysis - UNKNOWN"
            if k == "REAL_USER":
                return "B", "KEEP", "library analysis - REAL_USER"
            if re.match(r"(previews|enhanced|bundles|archives)$", aid):
                return "F", "SAFE", "playback / download caches"
            return "I", "UNKNOWN", "web/" + aid
        if sub == "jobs":
            jid = p[3] if len(p) > 3 else ""
            if jid in failed_jobs:
                return "H", "SAFE", "scratch of the FAILED analysis"
            c = job_class.get(jid)
            if c == "LIBRARY_RECORD":
                return "B", "REVIEW", "stand-alone job result shown in the library"
            if c == "LINKED_TO_ANALYSIS":
                return "A", "KEEP", "job trail of an analysis (job.json, logs)"
            if c == "ORPHAN":
                return "H", "SAFE", "orphan job"
            return "I", "UNKNOWN", "jobs/" + jid
        if sub == "inputs":
            aid = p[3] if len(p) > 3 else ""
            if aid in failed_assets:
                return "H", "SAFE", "scratch of the FAILED analysis"
            c = asset_class.get(aid)
            if c == "ORPHAN":
                return "H", "SAFE", "orphan input asset (no job, record or pipeline names it)"
            if c == "LIBRARY_RECORD":
                return "B", "REVIEW", "input of a stand-alone job result shown in the library"
            if c == "LINKED_TO_ANALYSIS":
                return "A", "KEEP", "input referenced by an analysis"
            return "I", "UNKNOWN", "inputs/" + aid
        if sub in ("smoke", "s2-validation", "s3-validation", "runtime") or sub.endswith((".log", ".json")):
            return "F", "SAFE", "old smoke output / logs / runtime markers"
        return "I", "UNKNOWN", "separation/" + sub
    if top == "reset-backups":
        return "G", "REVIEW", "reset-20261006 backup (5 study analyses, none in the DB)"
    if top == "ground-truth":
        sub = p[2] if len(p) > 2 else ""
        if sub in ("slakh", "freepats"):
            return "C", "KEEP", "license-clean benchmark sources (BabySlakh CC BY, FreePats CC0)"
        if sub in ("medleydb", "philharmonia"):
            return "E", "REVIEW", "license-excluded datasets (only the final_11 baseline reports used them)"
        if sub == "cases":
            return "D", "REVIEW", "case mixtures/references (regenerable from the sources above)"
        return "I", "UNKNOWN", "ground-truth/" + sub
    if top == "pad-eval":
        sub = p[2] if len(p) > 2 else ""
        if sub in ("stems", "tools"):
            return "C", "KEEP", "rendered synthetic GT stems + tools (clean benchmark source)"
        if sub in ("cases", "cases-v16"):
            return "D", "REVIEW", "case references / reports of the synthetic benchmark"
        return "D", "REVIEW", "pad-eval/" + sub
    if top in ("sample", "sample-b"):
        return "C", "KEEP", "demo song mix + stems"
    if top == "commercial-eval":
        return "C", "KEEP", "benchmark reports / metrics (commercial_13/6)"
    if top in ("part-studies",):
        return "C", "KEEP", "study reports"
    if top == "tmp-norbert":
        return "F", "SAFE", "isolated norbert wheel used for the Wiener experiment"
    if top == "audit":
        return "F", "SAFE", "this audit's own output"
    return "I", "UNKNOWN", top


seen = set(); buckets = defaultdict(lambda: [0, 0]); labels = defaultdict(lambda: [0, 0, "", ""]); logical = 0
for dirpath, _, names in os.walk(ROOT):
    for name in names:
        path = os.path.join(dirpath, name)
        try:
            st = os.lstat(path)
        except OSError:
            continue
        logical += st.st_size
        key = (st.st_dev, st.st_ino)
        if key in seen:
            continue
        seen.add(key)
        rel = os.path.relpath(path, ROOT).replace("\\", "/")
        cat, risk, label = classify(rel)
        buckets[(cat, risk)][0] += st.st_size; buckets[(cat, risk)][1] += 1
        l = labels[(cat, risk, label)]; l[0] += st.st_size; l[1] += 1
total = sum(v[0] for v in buckets.values()); gb = lambda n: f"{n / 2**30:,.2f} GB"
names_c = {"A": "PRODUCTION_REQUIRED", "B": "USER_PERSISTENT", "C": "TEST_FIXTURE_REQUIRED", "D": "REGENERABLE", "E": "DEV_TOOL", "F": "CACHE", "G": "LEGACY_BACKUP", "H": "ORPHAN", "I": "UNKNOWN"}
print(f"TOTAL physical {gb(total)} (logical {gb(logical)} - the difference is hard links)\n")
print("| Category | Risk | Size | Files |\n|---|---|---:|---:|")
for (cat, risk), (size, n) in sorted(buckets.items(), key=lambda kv: -kv[1][0]):
    print(f"| {cat} {names_c[cat]} | {risk} | {gb(size)} | {n:,} |")
by_risk = defaultdict(int)
for (cat, risk), (size, n) in buckets.items():
    by_risk[risk] += size
print("\nBY RISK:", {k: gb(v) for k, v in by_risk.items()})
print("\n| Path / reason | Category | Risk | Size | Files |\n|---|---|---|---:|---:|")
for (cat, risk, label), (size, n, _, _) in sorted(labels.items(), key=lambda kv: -kv[1][0])[:40]:
    print(f"| {label} | {cat} | {risk} | {gb(size)} | {n:,} |")
json.dump({"total": total, "buckets": {f"{c}|{r}": v for (c, r), v in buckets.items()},
           "labels": [{"label": l, "category": c, "risk": r, "bytes": v[0], "files": v[1]} for (c, r, l), v in labels.items()]},
          open(A / "classified.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
