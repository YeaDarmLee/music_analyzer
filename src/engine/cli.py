from __future__ import annotations

import argparse
import json

from engine.runner import run_experiment


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="music-engine")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run an experiment config end to end")
    r.add_argument("experiment")
    r.add_argument("--base-dir", default=".")
    r.add_argument("--resume")
    r.add_argument("--max-steps", type=int)
    a = p.parse_args(argv)
    res = run_experiment(a.experiment, a.base_dir, a.resume, a.max_steps)
    print(json.dumps({k: str(v) if not isinstance(v, (dict, int, float)) else v for k, v in res.items()},
                     indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
