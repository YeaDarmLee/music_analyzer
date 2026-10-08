"""Fixed pre-render (validation/test): one directory per scene in the project dataset format
    <split>_<idx>/ mix.wav, <atomic>.wav (active stems), metadata.json, provenance.json, spec.json
Inactive stems are not written (they are exactly zero by construction; QC enforces it before writing)."""
from __future__ import annotations

import json
import platform
from pathlib import Path

import numpy as np
import scipy

from . import assets as A
from .qc import qc_scene
from .scenes import Factory
from .targets import ATOMIC_ALL
from .util import hash_obj, sha256_array, write_wav


def render_fixed(factory: Factory, split: str, n: int, out_dir: str | Path, usage: str = "PRODUCTION_TRAINING",
                 git_commit: str = "") -> dict:
    out_dir, report = Path(out_dir), {"scenes": [], "failed": []}
    for i in range(n):
        spec = factory.make_spec(i, split, git_commit)
        problems = []
        try:
            A.gate(factory.records, spec.assets, usage)
        except A.ManifestError as e:
            problems = [str(e)]
        r = factory.render(spec)
        qc = qc_scene(r["mix"], r["atomic"], spec.active_stems, spec.sample_rate, spec.duration_samples,
                      manifest_problems=problems)
        if not qc.passed:
            report["failed"].append({"scene_id": spec.scene_id, "failures": qc.failures})
            continue
        d = out_dir / spec.scene_id
        write_wav(d / "mix.wav", r["mix"], spec.sample_rate)
        for s in spec.active_stems:
            write_wav(d / f"{s}.wav", r["atomic"][s], spec.sample_rate)
        meta = {"scene_id": spec.scene_id, "spec_hash": spec.hash(), "split": split, "active_stems": spec.active_stems,
                "all_stems": list(ATOMIC_ALL), "mix_seed": spec.seeds["mix"], "scene_type": spec.scene_type,
                "profile": spec.profile, "duration_samples": spec.duration_samples, "sample_rate": spec.sample_rate,
                "composition_family_id": spec.composition_family_id, "qc": qc.stats,
                "stem_sha256": {s: sha256_array(r["atomic"][s]) for s in spec.active_stems},
                "generator_version": spec.generator_version,
                "env": {"numpy": np.__version__, "scipy": scipy.__version__, "python": platform.python_version()}}
        prov = {"assets": {a: {k: v for k, v in factory.records[a].items() if k not in ("notes", "packet_ref", "root")}
                           for a in spec.assets}, "usage_checked": usage}
        prov["license_manifest_hash"] = hash_obj(prov["assets"])
        (d / "metadata.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
        (d / "provenance.json").write_text(json.dumps(prov, indent=1), encoding="utf-8")
        (d / "spec.json").write_text(json.dumps(spec.to_dict()), encoding="utf-8")
        report["scenes"].append(spec.scene_id)
    return report
