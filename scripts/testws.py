"""Test/benchmark workspace manager (see docs/SIX_TRACK_IMPROVEMENT_PLAN_KO.md section 4). Everything is a dry run unless --yes is given.

  testws.py usage | list | orphans
  testws.py new --est-gb 0.5 [--allow-gb 8 --reason "full-song eval"]
  testws.py clean --run-id ID [--yes]
  testws.py clean --all [--yes --confirm "DELETE ALL"]
  testws.py clean --all --include-reports [--yes --confirm "DELETE ALL INCLUDING REPORTS"]
  testws.py clean --older-than 7d [--yes]
  testws.py legacy-scan
  testws.py legacy-clean [--yes] [--approve L3,L5]     safe items go with --yes; 'confirm' items only when listed in --approve
"""
import argparse, json, sys
from music_analyzer import testws as t

gb = lambda n: f"{n / t.GB:.3f} GB"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["usage", "list", "orphans", "new", "clean", "legacy-scan", "legacy-clean"])
    ap.add_argument("--est-gb", type=float, default=0); ap.add_argument("--allow-gb", type=float); ap.add_argument("--reason", default="")
    ap.add_argument("--run-id"); ap.add_argument("--all", action="store_true"); ap.add_argument("--include-reports", action="store_true")
    ap.add_argument("--older-than"); ap.add_argument("--yes", action="store_true"); ap.add_argument("--confirm", default=""); ap.add_argument("--approve", default="")
    a = ap.parse_args(); dry = not a.yes
    try:
        if a.cmd == "usage":
            u = t.usage(); print(json.dumps({**u, "runs_bytes": gb(u["runs_bytes"]), "reports_bytes": gb(u["reports_bytes"]), "reclaimable_bytes": gb(u["reclaimable_bytes"]),
                                             "used_ratio": f"{u['used_ratio']:.1%}"}, indent=1, ensure_ascii=False))
        elif a.cmd == "list":
            for r in t.list_runs():
                print(f"{r['run_id']}  {r['state']:9}  {gb(r['bytes'])}")
        elif a.cmd == "orphans":
            for r in t.orphans():
                print(f"{r['run_id']}  {r['state']}  {gb(r['bytes'])}")
        elif a.cmd == "new":
            print(t.new_run(a.est_gb, a.allow_gb, a.reason))
        elif a.cmd == "clean":
            if a.run_id:
                n = t.clean_run(a.run_id, dry)
            elif a.all:
                n = t.clean_all(dry, a.confirm, a.include_reports)
            elif a.older_than:
                n = t.clean_older_than(float(a.older_than.rstrip("d")), dry)
            else:
                ap.error("clean needs --run-id, --all or --older-than")
            print(("would remove " if dry else "removed ") + gb(n) + ("  (dry run; add --yes)" if dry else ""))
        else:
            items = t.legacy_scan()
            for it in items:
                print(f"{it['id']:4} {it['class']:7} {gb(it['bytes']):>10}  {it['path']}  [{it['why']}]")
            if a.cmd == "legacy-clean":
                n = t.legacy_clean(items, set(filter(None, a.approve.split(","))), dry_run=dry)
                print(("would remove " if dry else "removed ") + gb(n) + ("  (dry run; add --yes)" if dry else ""))
    except t.TestWorkspaceError as e:
        sys.exit(f"refused: {e}")


if __name__ == "__main__":
    main()
