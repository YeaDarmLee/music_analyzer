"""Asset records, Packet-04/05 catalog, ingest (pin version + tree hash + license snapshot) and the Production gate.

Lifecycle: catalog entry (verdict from the research packet, version/sha256 = null)
  --ingest--> artifacts/assets/<id>.json (version, tree sha256, file count, bytes, downloaded_at, license snapshot hash)
  --gate----> engine.data.manifest policy (the shared dataset contract) for the requested usage class.
Until an asset is ingested its version/sha256 are null, so PRODUCTION_TRAINING rejects it.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from engine.data.manifest import POLICIES, ManifestError, manifest_hash, require_valid, validate_manifest

from .util import sha256_file, tree_sha256

REPO = Path(__file__).resolve().parents[2]
CATALOG = REPO / "configs" / "data_factory" / "asset_catalog.json"
ASSET_DIR = REPO / "artifacts" / "assets"
LICENSE_DIR = REPO / "artifacts" / "licenses"
INTERNAL_ASSET_ID = "project-procedural-dsp"  # synths, drum synthesis, FX, composition: code written for this project


def internal_asset_record() -> dict:
    """Own DSP/procedural material: no third-party rights involved. sha256 pins the generator version string."""
    from . import GENERATOR_VERSION
    from .util import hash_obj
    return {
        "asset_id": INTERNAL_ASSET_ID, "source": "Music Analyzer data_factory procedural DSP (project-written code)",
        "source_url": "repo:src/data_factory", "license": "project-owned", "license_url": "repo:src/data_factory",
        "version": GENERATOR_VERSION, "sha256": hash_obj({"generator": GENERATOR_VERSION}), "grade": "GREEN",
        "commercial_allowed": True, "training_allowed": True, "derivative_allowed": True, "redistribution_allowed": True,
        "attribution_required": False, "attribution_text": "", "notice_required": False, "downloaded_at": "n/a",
    }


def load_catalog(path: str | Path = CATALOG) -> dict[str, dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))["assets"]


def load_records(asset_dir: str | Path = ASSET_DIR) -> dict[str, dict]:
    """Ingested records override catalog entries; internal procedural asset is always present."""
    recs = {k: dict(v) for k, v in load_catalog().items()}
    for p in sorted(Path(asset_dir).glob("*.json")):
        r = json.loads(p.read_text(encoding="utf-8"))
        recs[r["asset_id"]] = r
    recs[INTERNAL_ASSET_ID] = internal_asset_record()
    return recs


def ingest_asset(asset_id: str, root: str | Path, version: str, license_file: str | Path,
                 asset_dir: str | Path = ASSET_DIR, license_dir: str | Path = LICENSE_DIR,
                 overrides: dict | None = None) -> dict:
    """Pin a downloaded asset: tree hash, version, license snapshot. Verdict fields come from the catalog and are
    never inferred from the files. `overrides` may only fill catalog gaps explicitly marked in the catalog notes."""
    cat = load_catalog()
    if asset_id not in cat:
        raise KeyError(f"{asset_id} is not in the asset catalog (no Packet verdict) -> cannot ingest")
    rec = dict(cat[asset_id])
    if rec["grade"] in ("RED",):
        raise ManifestError(f"{asset_id} is RED in the catalog and must not be ingested for training")
    tree, n_files, n_bytes = tree_sha256(root)
    lic_snapshot = Path(license_dir) / asset_id / "LICENSE.txt"
    lic_snapshot.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(license_file, lic_snapshot)
    rec.update(overrides or {})
    rec.update(version=version, sha256=tree, files=n_files, bytes=n_bytes, root=str(Path(root)),
               license_snapshot=f"artifacts/licenses/{asset_id}/LICENSE.txt", license_snapshot_sha256=sha256_file(lic_snapshot),
               downloaded_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    out = Path(asset_dir) / f"{asset_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
    return rec


def build_manifest(name: str, records: dict[str, dict], asset_ids_per_scene: dict[str, list[str]]) -> dict:
    """Dataset manifest in the engine's contract format. Only assets actually referenced by scenes are included."""
    used = sorted({a for ids in asset_ids_per_scene.values() for a in ids})
    missing = [a for a in used if a not in records]
    if missing:
        raise KeyError(f"unknown asset ids: {missing}")
    return {
        "manifest_version": 1, "name": name,
        "assets": {a: {k: v for k, v in records[a].items() if k not in ("notes", "packet_ref", "root")} for a in used},
        "samples": [{"sample_id": sid, "asset_ids": sorted(set(ids))} for sid, ids in sorted(asset_ids_per_scene.items())],
    }


def gate(records: dict[str, dict], asset_ids: list[str], usage: str) -> str:
    """Raise ManifestError unless every asset passes `usage`. Returns the hash of the checked mini-manifest."""
    if usage not in POLICIES:
        raise ManifestError(f"unknown usage {usage}")
    m = build_manifest("gate", records, {"gate": list(asset_ids)})
    return require_valid(m, usage)


__all__ = ["gate", "build_manifest", "ingest_asset", "load_records", "load_catalog", "manifest_hash",
           "validate_manifest", "ManifestError", "INTERNAL_ASSET_ID"]
