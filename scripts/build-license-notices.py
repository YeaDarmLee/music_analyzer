r"""Regenerate frontend/public/licenses/ and the internal production dependency manifest, or verify them (--check).

The notices are derived from the production plan (separation/configs/release_presets.json -> models -> commercial_approval.json,
runtime imports -> installed distributions), not from a hand-kept list. See music_analyzer/license_notices.py.

    .\.venv\Scripts\python.exe scripts\build-license-notices.py            # rebuild (fails on any production blocker)
    .\.venv\Scripts\python.exe scripts\build-license-notices.py --check    # exit 1 if committed notices are stale
"""
import argparse
import json
import sys
from pathlib import Path

from music_analyzer import license_notices, release

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/PRODUCTION_DEPENDENCY_MANIFEST.json"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        problems = license_notices.check()
        stale = json.loads(MANIFEST.read_text(encoding="utf-8")) != json.loads(json.dumps(release.manifest(), sort_keys=True)) if MANIFEST.exists() else True
        if stale:
            problems.append("docs/PRODUCTION_DEPENDENCY_MANIFEST.json is stale")
        print("\n".join(problems) or "notices and manifest are in sync")
        sys.exit(1 if problems else 0)
    try:
        notices = license_notices.build()
    except release.ReleaseError as error:
        sys.exit(error.detail)
    MANIFEST.write_text(json.dumps(release.manifest(), ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{len(notices['components']['server'])} server, {len(notices['components']['web'])} web, {len(notices['models'])} model entries")


if __name__ == "__main__":
    main()
