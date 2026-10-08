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

KIT_RULES = [("hat_open", re.compile(r"(open|ohh|hito(?!c))", re.I), re.compile(r"(hat|hh)", re.I)),
             ("hat_closed", re.compile(r"(hihat|hi-hat|hat|hh|chh|closed)", re.I), None),
             ("kick", re.compile(r"(kick|bass[ _]?drum|bdrum|\bbd\b)", re.I), None),
             ("snare", re.compile(r"(snare|\bsd\b)", re.I), None),
             ("tom", re.compile(r"tom", re.I), None),
             ("crash", re.compile(r"(crash|cymbal)", re.I), None)]


VEL_RE = re.compile(r"(?:^|[_\- ])v(\d)(?:[_\- .]|$)", re.I)


def drumkit_manifest(root: Path, asset_id: str, instrument_id: str, version: str, license: str, sha: str,
                     exts=(".wav",), exclude_prefixes=(), include_prefixes=(), name_include=None, name_exclude=None) -> tuple[dict, dict]:
    """One-shot kit from a directory tree. Role comes from path keywords (KIT_RULES), velocity layers from `_v<k>_`
    tokens in the file name (layers split the 1..127 range evenly), same-layer files become random round-robin."""
    roles: dict[str, dict[int, list[str]]] = {}
    unmatched = excluded = 0
    for p in sorted(root.rglob("*")):
        if p.suffix.lower() not in exts:
            continue
        name = p.relative_to(root).as_posix()
        if (any(name.startswith(x) for x in exclude_prefixes) or (include_prefixes and not any(name.startswith(x) for x in include_prefixes))
                or (name_include and not re.search(name_include, name, re.I)) or (name_exclude and re.search(name_exclude, name, re.I))):
            excluded += 1
            continue
        for role, rx, also in KIT_RULES:
            if rx.search(name) and (also is None or also.search(name)):
                m = VEL_RE.search(p.name)
                roles.setdefault(role, {}).setdefault(int(m.group(1)) if m else 0, []).append(name)
                break
        else:
            unmatched += 1
    zones = []
    for role, layers in roles.items():
        keys = sorted(layers)
        for li, layer in enumerate(keys):
            lo = 1 + (127 * li) // len(keys)
            hi = (127 * (li + 1)) // len(keys)
            files = layers[layer]
            for j, f in enumerate(files):
                zones.append({"sample": f, "root_key": DRUM_KEYS[role], "lo_key": DRUM_KEYS[role], "hi_key": DRUM_KEYS[role],
                              "lo_vel": lo, "hi_vel": hi, "volume_db": 0.0, "pan": 0.0, "tune_cents": 0.0, "offset": 0,
                              "keytrack": False, "one_shot": True, "rand": [j / len(files), (j + 1) / len(files)]})
    man = {"instrument_id": instrument_id, "asset_id": asset_id, "kind": "drumkit", "source_version": version,
           "license": license, "source_sha256": sha, "exclude_prefixes": list(exclude_prefixes),
           "include_prefixes": list(include_prefixes), "name_include": name_include, "name_exclude": name_exclude, "zones": zones}
    return man, {"roles": {r: sum(len(v) for v in l.values()) for r, l in roles.items()}, "unmatched_files": unmatched,
                 "excluded_files": excluded}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="data-factory")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("catalog")
    i = sub.add_parser("ingest-asset")
    i.add_argument("--id", required=True); i.add_argument("--root", required=True)
    i.add_argument("--version", required=True); i.add_argument("--license-file", required=True)
    s = sub.add_parser("ingest-sfz")
    s.add_argument("--asset-id", required=True); s.add_argument("--sfz", action="append", required=True,
                  help="path[::opcode=value,opcode=value]; repeat to merge several files")
    s.add_argument("--cc", action="append", default=[], help="fixed controller state N=VALUE, e.g. 64=127 (sustain pedal down)")
    s.add_argument("--cc-variant", action="append", default=[], help="NAME:N=V alternative fixed controller state, e.g. pedal_up:64=0")
    s.add_argument("--base-dir", default=None, help="sample= paths are relative to this dir under the asset root")
    s.add_argument("--instrument-id", required=True); s.add_argument("--out", required=True)
    s.add_argument("--kind", default="pitched"); s.add_argument("--lenient", action="store_true")
    d = sub.add_parser("ingest-drumkit")
    d.add_argument("--asset-id", required=True); d.add_argument("--subdir", default=".")
    d.add_argument("--instrument-id", required=True); d.add_argument("--out", required=True)
    d.add_argument("--exclude", action="append", default=[]); d.add_argument("--include", action="append", default=[])
    d.add_argument("--name-include"); d.add_argument("--name-exclude")
    cf = sub.add_parser("convert-flac", help="decode the FLAC samples referenced by an instrument manifest to float32 WAV (derived copy)")
    cf.add_argument("--manifest", required=True); cf.add_argument("--out-dir", required=True)
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
        root = Path(rec["root"]) if Path(rec["root"]).is_absolute() else A.REPO / rec["root"]
        if a.cmd == "ingest-sfz":
            items = []
            for spec in a.sfz:
                path, _, ov = spec.partition("::")
                items.append((root / path if not Path(path).is_absolute() else Path(path),
                              dict(kv.split("=", 1) for kv in ov.split(",") if kv)))
            man, rep = build_manifest_from_sfz(items, root, a.instrument_id, a.asset_id, rec["version"], rec["license"],
                                               rec["sha256"], a.kind, strict=not a.lenient, base_dir=a.base_dir,
                                               cc_state={int(k): int(v) for k, v in (c.split("=") for c in a.cc)} or None,
                                               cc_variants={n: {int(k): int(v) for k, v in (c.split("=") for c in [st])}
                                                            for n, st in (x.split(":", 1) for x in a.cc_variant)} or None)
        else:
            man, rep = drumkit_manifest(root / a.subdir, a.asset_id, a.instrument_id, rec["version"], rec["license"], rec["sha256"],
                                        exclude_prefixes=tuple(a.exclude), include_prefixes=tuple(a.include),
                                        name_include=a.name_include, name_exclude=a.name_exclude)
            for z in man["zones"]:
                z["sample"] = (Path(a.subdir) / z["sample"]).as_posix() if a.subdir != "." else z["sample"]
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(man, indent=1), encoding="utf-8")
        print(json.dumps(rep, indent=1))
    elif a.cmd == "convert-flac":
        import soundfile as sf  # ingest-time only; runtime reads plain WAV with scipy
        from .util import write_wav
        man = json.loads(Path(a.manifest).read_text(encoding="utf-8"))
        rec = A.load_records()[man["asset_id"]]
        root = Path(rec["root"]) if Path(rec["root"]).is_absolute() else A.REPO / rec["root"]
        out = Path(a.out_dir)
        n = 0
        for z in man["zones"] + (man.get("zones_pedal_up") or []):
            src = root / z["sample"]
            if src.suffix.lower() != ".flac":
                continue
            dst = out / Path(z["sample"]).with_suffix(".wav")
            if not dst.exists():
                x, sr_ = sf.read(str(src), dtype="float32", always_2d=True)
                write_wav(dst, x.T, sr_)
            z["sample"] = Path(z["sample"]).with_suffix(".wav").as_posix()
            n += 1
        man["sample_root"] = str(out.resolve().relative_to(A.REPO).as_posix()) if out.resolve().is_relative_to(A.REPO) else str(out.resolve())
        man["conversion"] = {"from": "flac", "to": "wav float32", "tool": f"python-soundfile {sf.__version__} / libsndfile {sf.__libsndfile_version__}",
                             "scope": "ingest-time only", "source_asset_sha256": rec["sha256"], "files": n}
        Path(a.manifest).write_text(json.dumps(man, indent=1), encoding="utf-8")
        print(json.dumps(man["conversion"], indent=1))
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
