"""DF-0 ingest: pin already-downloaded assets (git checkouts / archives) into artifacts/assets + artifacts/licenses.
Downloads themselves are manual (commands are recorded in docs/legal/ASSET_DOWNLOADS.md).

usage: python scripts/df0_ingest.py git <asset_id> <checkout_dir> [license_relpath]
       python scripts/df0_ingest.py zip <asset_id> <zip_path> <extract_dir> --url URL [--md5 MD5] [--license-file F | --license-text FILE]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from data_factory import assets as A  # noqa: E402
from data_factory.util import sha256_file  # noqa: E402


def git(d, *a):
    return subprocess.run(["git", "-C", str(d), *a], capture_output=True, text=True, check=True).stdout.strip()


def md5_file(p):
    h = hashlib.md5()
    with open(p, "rb") as f:
        while b := f.read(1 << 22):
            h.update(b)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="kind", required=True)
    g = sub.add_parser("git"); g.add_argument("asset_id"); g.add_argument("checkout"); g.add_argument("license", nargs="?", default="LICENSE")
    z = sub.add_parser("zip"); z.add_argument("asset_id"); z.add_argument("zip_path"); z.add_argument("extract_dir")
    z.add_argument("--url", required=True); z.add_argument("--md5"); z.add_argument("--license-file", required=True)
    z.add_argument("--subdir", default=".", help="directory inside the extraction to treat as the asset root")
    a = ap.parse_args()
    if a.kind == "git":
        d = Path(a.checkout).resolve()
        commit = git(d, "rev-parse", "HEAD")
        extra = {"source_commit": commit, "source_commit_date": git(d, "log", "-1", "--format=%cI"),
                 "source_remote": git(d, "remote", "get-url", "origin"), "retrieval": "git clone --depth 1"}
        rec = A.ingest_asset(a.asset_id, d, commit, d / a.license, overrides=extra)
    else:
        zp, ex = Path(a.zip_path).resolve(), Path(a.extract_dir).resolve()
        got_md5 = md5_file(zp)
        if a.md5 and a.md5 != got_md5:
            raise SystemExit(f"md5 mismatch: expected {a.md5}, got {got_md5}")
        if not ex.exists():
            with zipfile.ZipFile(zp) as zf:
                bad = zf.testzip()
                if bad:
                    raise SystemExit(f"corrupt member {bad}")
                zf.extractall(ex)
        root = (ex / a.subdir).resolve()
        extra = {"archive_url": a.url, "archive_name": zp.name, "archive_bytes": zp.stat().st_size, "archive_md5": got_md5,
                 "archive_sha256": sha256_file(zp), "retrieval": "https download + zip extract"}
        rec = A.ingest_asset(a.asset_id, root, extra["archive_sha256"][:16], a.license_file, overrides=extra)
    print(json.dumps({k: rec.get(k) for k in ("asset_id", "grade", "license", "version", "sha256", "files", "bytes", "source_commit",
                                              "archive_sha256", "archive_md5", "license_snapshot_sha256", "root")}, indent=1))


if __name__ == "__main__":
    main()
