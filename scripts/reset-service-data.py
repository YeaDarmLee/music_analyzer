"""Reset the service to a clean slate: every analysis, job, input, scratch/benchmark/evaluation dataset and every analysis-related DB row goes;
code, docs, git, checkpoints (data/separation/models), tools, the license/approval records, DB schema and the USER ACCOUNTS stay.

usage: reset-service-data.py            dry run (prints what would be removed, touches nothing)
       reset-service-data.py --apply    do it
Refuses to run while a server listens on the service port (default 8780).
DB: analysis_owners, sessions, auth_attempts, user_consents are emptied; users is kept (consents are re-requested at next login).
"""
import argparse, json, os, shutil, socket, stat, sys
from pathlib import Path
from music_analyzer.auth import AuthStore

ROOT = Path(__file__).resolve().parents[1]; DATA = ROOT / "data"
# Everything below data/ is generated; these are the only things kept inside data/separation.
KEEP_IN_SEPARATION = {"models", "tools", "environment", "runtime"}
CLEAR_TABLES = ["analysis_owners", "sessions", "auth_attempts", "user_consents"]  # FK order: children first; users untouched
size_of = lambda p: sum(f.stat().st_size for f in Path(p).rglob("*") if f.is_file()) if Path(p).is_dir() else (Path(p).stat().st_size if Path(p).exists() else 0)
gb = lambda n: f"{n / 2**30:.2f} GB"


def remove(path):
    def writable(function, target, _):
        os.chmod(target, stat.S_IWRITE); function(target)
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, onerror=writable)
    elif path.exists() or path.is_symlink():
        os.chmod(path, stat.S_IWRITE); path.unlink()


def targets():
    found = []
    for entry in sorted(DATA.iterdir()):
        if entry.name == "separation":
            for inner in sorted(entry.iterdir()):
                if inner.name == "runtime":
                    found.extend(inner.iterdir())  # old server logs and caches; the directory itself stays
                elif inner.name not in KEEP_IN_SEPARATION:
                    found.append(inner)
        else:
            found.append(entry)
    for name in ("web",):  # stray root-level directory from an old layout (empty)
        stray = ROOT / name
        if stray.is_dir() and not any(stray.iterdir()):
            found.append(stray)
    for cache in ROOT.glob("separation/**/__pycache__"):
        found.append(cache)
    for cache in (ROOT / "separation/.pytest_cache", ROOT / ".pytest_cache"):
        if cache.exists():
            found.append(cache)
    return found


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--apply", action="store_true"); parser.add_argument("--port", type=int, default=8780)
    args = parser.parse_args()
    with socket.socket() as probe:
        probe.settimeout(.5)
        if probe.connect_ex(("127.0.0.1", args.port)) == 0:
            sys.exit(f"refusing: a server is listening on port {args.port}; stop it first")
    store = AuthStore()
    before = {t: store.query(f"SELECT COUNT(*) c FROM {t}")[0]["c"] for t in ("users", *CLEAR_TABLES)}
    assert before["users"] > 0, "no users: refusing to reset (wrong database?)"
    plan = [(p, size_of(p)) for p in targets()]
    print(f"{'APPLY' if args.apply else 'DRY RUN'}  database={store.settings.get('MYSQL_DATABASE', 'music_analyzer')}  rows before: {before}")
    for path, size in sorted(plan, key=lambda x: -x[1])[:30]:
        print(f"  {gb(size):>9}  {path.relative_to(ROOT)}")
    print(f"  total to remove: {gb(sum(s for _, s in plan))} in {len(plan)} entries")
    if not args.apply:
        return
    for path, _ in plan:
        if path.exists() or path.is_symlink():
            remove(path)
    for table in CLEAR_TABLES:
        store.query(f"DELETE FROM {table}")
    after = {t: store.query(f"SELECT COUNT(*) c FROM {t}")[0]["c"] for t in ("users", *CLEAR_TABLES)}
    assert after["users"] == before["users"] and all(after[t] == 0 for t in CLEAR_TABLES), after
    orphans = store.query("SELECT (SELECT COUNT(*) FROM analysis_owners a LEFT JOIN users u ON u.id=a.user_id WHERE u.id IS NULL) + "
                          "(SELECT COUNT(*) FROM sessions a LEFT JOIN users u ON u.id=a.user_id WHERE u.id IS NULL) + "
                          "(SELECT COUNT(*) FROM user_consents a LEFT JOIN users u ON u.id=a.user_id WHERE u.id IS NULL) AS n")[0]["n"]
    assert orphans == 0, orphans
    print("rows after:", after, "| orphan rows:", orphans)
    print(json.dumps({"data_remaining": sorted(p.name for p in DATA.iterdir()), "separation_remaining": sorted(p.name for p in (DATA / "separation").iterdir())}))


main()
