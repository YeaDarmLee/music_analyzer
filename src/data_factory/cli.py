"""Data Factory command line: asset ingest (DF-0), instrument manifests, vocal index, fixed renders, license manifest."""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

from . import assets as A
from .sampler import build_manifest_from_sfz
from .synth import DRUM_KEYS
from .util import tree_sha256
from .vocal import build_vocal_index, save_index

KIT_RULES = [("hat_open", re.compile(r"(open|ohh)", re.I), re.compile(r"(hat|hh)", re.I)),
             ("hat_closed", re.compile(r"(hihat|hi-hat|hat|hh|chh|closed)", re.I), None),
             ("kick", re.compile(r"(kick|bassdrum|bass_drum|\bbd\b)", re.I), None),
             ("snare", re.compile(r"(snare|\bsd\b|rim)", re.I), None),
             ("tom", re.compile(r"tom", re.I), None),
             ("crash", re.compile(r"(crash|cymbal)", re.I), None)]


def drumkit_manifest(root: Path, asset_id: str, instrument_id: str, version: str, license: str, sha: str,
                     exts=(".wav",)) -> tuple[dict, dict]:
    roles: dict[str, list[str]] = {}
    unmatched = 0
    for p in sorted(root.rglob("*")):
        if p.suffix.lower() not in exts:
            continue
        name = p.relative_to(root).as_posix()
        for role, rx, also in KIT_RULES:
            if rx.search(name) and (also is None or also.search(name)):
                roles.setdefault(role, []).append(name)
                break
        else:
            unmatched += 1
    zones = []
    for role, files in roles.items():
        k = len(files)
        for j, f in enumerate(files):
            zones.append({"sample": f, "root_key": DRUM_KEYS[role], "lo_key": DRUM_KEYS[role], "hi_key": DRUM_KEYS[role],
                          "lo_vel": 1, "hi_vel": 127, "volume_db": 0.0, "pan": 0.0, "tune_cents": 0.0, "offset": 0,
                          "keytrack": False, "one_shot": True, "rand": [j / k, (j + 1) / k]})
    man = {"instrument_id": instrument_id, "asset_id": asset_id, "kind": "drumkit", "source_version": version,
           "license": license, "source_sha256": sha, "zones": zones}
    return man, {"roles": {r: len(f) for r, f in roles.items()}, "unmatched_files": unmatched}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="data-factory")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("catalog")
    i = sub.add_parser("ingest-asset")
    i.add_argument("--id", required=True); i.add_argument("--root", required=True)
    i.add_argument("--version", required=True); i.add_argument("--license-file", required=True)
    s = sub.add_parser("ingest-sfz")
    s.add_argument("--asset-id", required=True); s.add_argument("--sfz", required=True)
    s.add_argument("--instrument-id", required=True); s.add_argument("--out", required=True)
    s.add_argument("--kind", default="pitched"); s.add_argument("--lenient", action="store_true")
    d = sub.add_parser("ingest-drumkit")
    d.add_argument("--asset-id", required=True); d.add_argument("--subdir", default=".")
    d.add_argument("--instrument-id", required=True); d.add_argument("--out", required=True)
    v = sub.add_parser("index-vocalset")
    v.add_argument("--root", required=True); v.add_argument("--out", required=True)
    m = sub.add_parser("manifest", help="license/dataset manifest (engine contract) for the first N scenes of each split")
    m.add_argument("--config", required=True); m.add_argument("--out", required=True)
    m.add_argument("--usage", default="PRODUCTION_TRAINING"); m.add_argument("--train", type=int, default=0)
    m.add_argument("--val", type=int, default=0)
    r = sub.add_parser("render-fixed")
    r.add_argument("--config", required=True); r.add_argument("--split", required=True)
    r.add_argument("-n", type=int, required=True); r.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    if a.cmd == "catalog":
        for k, v_ in A.load_records().items():
            print(f"{v_['grade']:18s} {k:28s} version={v_.get('version')} sha={str(v_.get('sha256'))[:12]}")
    elif a.cmd == "ingest-asset":
        rec = A.ingest_asset(a.id, a.root, a.version, a.license_file)
        print(json.dumps({k: rec[k] for k in ("asset_id", "version", "sha256", "files", "bytes", "grade")}, indent=1))
    elif a.cmd in ("ingest-sfz", "ingest-drumkit"):
        rec = A.load_records()[a.asset_id]
        root = Path(rec["root"])
        if a.cmd == "ingest-sfz":
            man, rep = build_manifest_from_sfz(a.sfz, root, a.instrument_id, a.asset_id, rec["version"], rec["license"],
                                               rec["sha256"], a.kind, strict=not a.lenient)
        else:
            man, rep = drumkit_manifest(root / a.subdir, a.asset_id, a.instrument_id, rec["version"], rec["license"], rec["sha256"])
            for z in man["zones"]:
                z["sample"] = (Path(a.subdir) / z["sample"]).as_posix() if a.subdir != "." else z["sample"]
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(man, indent=1), encoding="utf-8")
        print(json.dumps(rep, indent=1))
    elif a.cmd == "index-vocalset":
        rec = A.load_records()["vocalset"]
        idx = build_vocal_index(a.root)
        save_index(idx, a.out)
        print(json.dumps({"clips": len(idx["clips"]), "excluded": idx["excluded"], "singers": len(idx["singer_split"]),
                          "split": idx["singer_split"]}, indent=1))
    elif a.cmd == "manifest":
        from .scenes import Factory
        from engine.data.manifest import require_valid
        f = Factory.from_yaml(a.config)
        per = {}
        for split, n in (("train", a.train), ("val", a.val)):
            for i in range(n):
                sp = f.make_spec(i, split)
                per[sp.scene_id] = sp.assets
        man = A.build_manifest("data_factory_scenes", f.records, per)
        sha = require_valid(man, a.usage)
        Path(a.out).write_text(json.dumps(man, indent=1), encoding="utf-8")
        print(json.dumps({"scenes": len(per), "assets": sorted(man["assets"]), "manifest_sha256": sha, "usage": a.usage}, indent=1))
    elif a.cmd == "render-fixed":
        from .fixed import render_fixed
        from .scenes import Factory
        t0 = time.time()
        rep = render_fixed(Factory.from_yaml(a.config), a.split, a.n, a.out)
        print(json.dumps({"ok": len(rep["scenes"]), "failed": rep["failed"], "seconds": round(time.time() - t0, 1)}, indent=1))
        return 1 if rep["failed"] else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
