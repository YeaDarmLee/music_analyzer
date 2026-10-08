"""Inventory / dry-run / apply for generated test, benchmark and diagnostic data under data/.

Dry run is the default and deletes nothing. `--apply` deletes exactly what the dry run lists as DELETE.
Safety rules (not path-name guesses):
  * nothing git-tracked is ever deleted (git ls-files is checked for every candidate file)
  * checkpoint / soundfont / config files (.ckpt .pt .pth .safetensors .onnx .sf2 .yaml .yml) are never deleted
  * a file with another hard link (the eval libraries hard-link data/separation/models/*) is unlinked but its size is NOT counted as reclaimed
  * KEEP rules win over DELETE rules; anything that matches no rule is reported as UNCLASSIFIED and kept
  * data/separation/{models,tools,web,jobs,inputs} and data/reset-backups are the application's own data / user backups: always KEEP here
usage: storage-inventory.py [--apply] [--json OUT]
"""
import argparse, fnmatch, json, os, subprocess, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; DATA = ROOT / "data"
PROTECT_EXT = {".ckpt", ".pt", ".pth", ".safetensors", ".onnx", ".sf2", ".yaml", ".yml"}
REPORT_NAMES = {"report.json", "prepared.json", "case.json", "run.json", "comparison.json"}
GENERATED_DIRS = ("library", "evaluation-candidates", "evaluation-outputs", "without-recovery", "evaluation-references")

# (category, action, reason, glob on posix path relative to data/). First match wins.
RULES = [
    ("application data", "KEEP", "model checkpoints, runtime tools", "separation/models/**"),
    ("application data", "KEEP", "tool binaries", "separation/tools/**"),
    ("user library", "KEEP", "the app's own analyses (web/jobs/inputs): decision belongs to the user", "separation/web/**"),
    ("user library", "KEEP", "the app's own analyses (web/jobs/inputs): decision belongs to the user", "separation/jobs/**"),
    ("user library", "KEEP", "the app's own analyses (web/jobs/inputs): decision belongs to the user", "separation/inputs/**"),
    ("user backup", "KEEP", "backup made by an earlier library reset", "reset-backups/**"),
    ("source dataset", "KEEP", "downloaded external datasets (not generated)", "ground-truth/slakh/**"),
    ("source dataset", "KEEP", "downloaded external datasets (not generated)", "ground-truth/medleydb/**"),
    ("source dataset", "KEEP", "downloaded external datasets (not generated)", "ground-truth/philharmonia/**"),
    ("source dataset", "KEEP", "downloaded external datasets (not generated)", "ground-truth/freepats/**"),
    ("synthetic GT source", "KEEP", "rendered stems + tools the benchmarks score against", "pad-eval/stems/**"),
    ("synthetic GT source", "KEEP", "rendered stems + tools the benchmarks score against", "pad-eval/tools/**"),
    ("synthetic GT source", "KEEP", "rendered stems + tools the benchmarks score against", "pad-eval/test.*"),
    ("sample source", "KEEP", "demo mix and stems (frontend/public/samples is built from them)", "sample/stems/**"),
    ("sample source", "KEEP", "demo mix and stems", "sample/mix.wav"),
    ("sample source", "KEEP", "demo mix and stems", "sample-b/stems/**"),
    ("sample source", "KEEP", "demo mix and stems", "sample-b/mix.wav"),
    # GT references of the clean synthetic benchmark (cases-v16 is what commercial evals score against)
    ("clean benchmark GT", "KEEP", "evaluation-references of the license-clean pad cases, needed to rescore", "pad-eval/cases-v16/*/evaluation-references/**"),
    ("test runs", "DELETE", "scratch libraries of unit-test runs (everything inside, including their prepared.json)", "test-runs/**"),
    ("test temp", "DELETE", "scratch libraries of unit-test runs", "test-tmp-*/**"),
    ("commercial eval copies", "DELETE", "copies of the pad-eval references (regenerable from pad-eval/cases-v16)", "commercial-eval/**/evaluation-references/**"),
    ("model output", "DELETE", "pipeline library of a benchmark run (jobs/inputs/web of that run)", "**/library/**"),
    ("model output", "DELETE", "pipeline library of a benchmark run", "**/*-library/**"),
    ("case input", "KEEP", "GT mixture other cases and rescoring depend on", "**/mix.wav"),
    ("case input", "KEEP", "GT references other cases depend on (regenerable only by re-running prepare)", "**/references/**"),
    ("case input", "KEEP", "GT references (regenerable only by re-running prepare)", "**/evaluation-references/**"),
    ("report / provenance", "KEEP", "reports, prepared, run, case configuration (small)", "**/*.json"),
    ("report / provenance", "KEEP", "notes", "**/*.md"),
    ("report / provenance", "KEEP", "notes", "**/*.txt"),
    ("report / provenance", "KEEP", "metrics", "**/*.csv"),
    # generated benchmark audio
    ("old GT case runs", "DELETE", "per-version baseline case outputs; reports are kept", "ground-truth/cases/**"),
    ("old pad case runs", "DELETE", "pad-eval cases v1..v15 outputs; reports are kept", "pad-eval/cases/**"),
    ("pad v16 outputs", "DELETE", "comparison audio of the final_11 baseline run; reports and references are kept", "pad-eval/cases-v16/**"),
    ("head study cache", "DELETE", "Mega53 head arrays written by scripts/study-pad-heads.py (regenerable)", "pad-eval/heads/**"),
    ("commercial eval", "DELETE", "commercial_13/6 benchmark libraries and listening audio; reports are kept", "commercial-eval/**"),
    ("part studies", "DELETE", "per-study audio outputs", "part-studies/**"),
    ("test runs", "DELETE", "test-run libraries", "test-runs/**"),
    ("test temp", "DELETE", "test temporary libraries", "test-tmp-*/**"),
    ("sample library", "DELETE", "pipeline library of the demo render (the deliverable is in frontend/public/samples)", "sample/library/**"),
    ("sample library", "DELETE", "pipeline library of the demo render", "sample-b/library/**"),
]


KINDS = {"application data": "canonical source / fixture", "user library": "canonical source / fixture", "user backup": "canonical source / fixture",
         "source dataset": "canonical source / fixture", "synthetic GT source": "canonical source / fixture", "sample source": "canonical source / fixture",
         "case input": "regenerable generated input", "commercial eval copies": "regenerable generated input", "head study cache": "regenerable generated input",
         "report / provenance": "report / provenance", "clean benchmark GT": "regenerable generated input"}


def tracked():
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True).stdout.decode("utf-8", "replace")
    return {(ROOT / p).resolve() for p in out.split("\0") if p}


def model_inodes():
    """(dev, inode) of every real checkpoint under data/separation/models: a protected-extension file sharing one of them is only an extra name."""
    result = set()
    for path in (DATA / "separation/models").rglob("*"):
        try:
            if path.is_file():
                stat = path.stat(); result.add((stat.st_dev, stat.st_ino))
        except OSError:
            pass
    return result


def classify(rel: str):
    for category, action, reason, pattern in RULES:
        if fnmatch.fnmatch(rel, pattern) or (pattern.startswith("**/") and fnmatch.fnmatch(rel, pattern[3:])) or (pattern.startswith("**/") and rel.endswith(pattern[2:])):
            return category, action, reason
    return "unclassified", "KEEP", "no rule matches; left alone"


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--json")
    args = ap.parse_args()
    git = tracked(); real_models = model_inodes()
    plan = defaultdict(lambda: {"files": 0, "bytes": 0, "reclaim": 0, "action": "", "reason": ""})
    victims, protected, dirs_seen = [], [], defaultdict(int)
    for dirpath, _, names in os.walk(DATA):
        for name in names:
            path = Path(dirpath) / name
            rel = path.relative_to(DATA).as_posix()
            try:
                stat = path.stat()
            except OSError:
                continue
            category, action, reason = classify(rel)
            alias = path.suffix.lower() in PROTECT_EXT and (stat.st_dev, stat.st_ino) in real_models and stat.st_nlink > 1   # extra name of a real checkpoint
            if action == "DELETE" and (path.resolve() in git or (path.suffix.lower() in PROTECT_EXT and not alias)):
                protected.append((rel, "git-tracked" if path.resolve() in git else "checkpoint/config extension")); action = "KEEP"; reason = "protected"
            if action == "DELETE" and name in REPORT_NAMES and category not in ("test runs", "test temp"):
                action, reason = "KEEP", "report"
            top = rel.split("/")[0] + "/" + (rel.split("/")[1] if "/" in rel and rel.split("/")[0] in ("separation", "commercial-eval", "pad-eval", "ground-truth") else "")
            key = (category, action, top.rstrip("/"))
            entry = plan[key]; entry["files"] += 1; entry["bytes"] += stat.st_size; entry["action"] = action; entry["reason"] = reason
            if action == "DELETE":
                if stat.st_nlink == 1:
                    entry["reclaim"] += stat.st_size
                victims.append(path)
            parts = rel.split("/")
            for depth in range(1, min(len(parts), 4)):
                dirs_seen["/".join(parts[:depth])] += stat.st_size
    fmt = lambda n: f"{n / 2**30:,.2f} GB" if n >= 2**30 else f"{n / 2**20:,.1f} MB"
    print("| Kind | Category | Path | Files | Size | Reclaimable | Action | Why |\n|---|---|---|---:|---:|---:|---|---|")
    rows = sorted(plan.items(), key=lambda kv: -kv[1]["bytes"])
    for (category, action, top), e in rows:
        print(f"| {KINDS.get(category, 'generated model output' if action == 'DELETE' else 'unclassified')} | {category} | data/{top} | {e['files']:,} | {fmt(e['bytes'])} | {fmt(e['reclaim']) if action == 'DELETE' else '-'} | {action} | {e['reason']} |")
    delete = [e for (c, a, t), e in plan.items() if a == "DELETE"]; keep = [e for (c, a, t), e in plan.items() if a == "KEEP"]
    totals = {"delete_files": sum(e["files"] for e in delete), "delete_bytes": sum(e["bytes"] for e in delete),
              "reclaimable_bytes": sum(e["reclaim"] for e in delete), "keep_files": sum(e["files"] for e in keep), "keep_bytes": sum(e["bytes"] for e in keep)}
    print(f"\nDELETE: {totals['delete_files']:,} files, {fmt(totals['delete_bytes'])} listed, {fmt(totals['reclaimable_bytes'])} actually reclaimable (hard links excluded)")
    print(f"KEEP:   {totals['keep_files']:,} files, {fmt(totals['keep_bytes'])}")
    print(f"protected inside delete categories: {len(protected)}")
    for rel, why in protected[:10]:
        print(f"  protected {rel} ({why})")
    print("\nTOP 20 directories (depth <= 3):")
    for rel, size in sorted(dirs_seen.items(), key=lambda kv: -kv[1])[:20]:
        print(f"  {fmt(size):>10}  data/{rel}  [{classify(rel + '/x')[1]}]")
    if args.json:
        Path(args.json).write_text(json.dumps({"totals": totals, "rows": [{"category": c, "action": a, "path": t, **e} for (c, a, t), e in rows],
                                               "protected": protected}, ensure_ascii=False, indent=2), encoding="utf-8")
    # every source a surviving prepared.json names must still exist after the deletion (benchmarks stay regenerable from the same sources)
    doomed = {p.resolve() for p in victims}; broken = []
    for prepared in DATA.rglob("prepared.json"):
        if prepared.resolve() in doomed:
            continue
        try:
            sources = json.loads(prepared.read_text(encoding="utf-8")).get("sources", [])
        except (OSError, ValueError):
            continue
        for item in sources:
            path = Path(item["path"]).resolve()
            if path in doomed or not path.exists():
                broken.append((prepared.relative_to(DATA).as_posix(), item["path"]))
    print(f"\nsource dependency check: {len(broken)} broken reference(s)")
    for prepared, path in broken[:10]:
        print("  BROKEN", prepared, "->", path)
    if args.apply and broken:
        sys.exit("refusing to delete: a surviving prepared.json would lose its source")
    if args.apply:
        removed = freed = 0
        for path in victims:
            try:
                size = path.stat().st_size if path.stat().st_nlink == 1 else 0
                path.unlink(); removed += 1; freed += size
            except OSError as error:
                print("failed", path, error, file=sys.stderr)
        for dirpath, dirnames, filenames in os.walk(DATA, topdown=False):   # remove directories left empty
            if Path(dirpath) != DATA and not dirnames and not filenames:
                try: Path(dirpath).rmdir()
                except OSError: pass
        print(f"\nAPPLIED: removed {removed:,} files, reclaimed {fmt(freed)}")


main()
