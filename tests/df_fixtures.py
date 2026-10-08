"""Test-only fixture assets (procedurally generated tones/noise). They are written to tmp dirs, ingested under catalog ids
only inside the test's private artifact directories, and never appear in production manifests."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np
import yaml

from data_factory import assets as A
from data_factory.scenes import Factory
from data_factory.sfz import note_to_midi  # noqa: F401
from data_factory.util import write_wav

REPO = Path(__file__).resolve().parents[1]
SR = 44100


def tone(f, dur, sr=SR, decay=1.5, seed=0):
    t = np.arange(int(dur * sr)) / sr
    y = sum(np.sin(2 * np.pi * f * k * t) / k for k in (1, 2, 3, 4)) * np.exp(-t / decay)
    return (0.3 * y / np.abs(y).max()).astype(np.float32)[None]


def noise_hit(dur, seed, sr=SR):
    r = np.random.RandomState(seed)
    t = np.arange(int(dur * sr)) / sr
    return (0.5 * r.randn(len(t)) * np.exp(-t / (dur / 4))).astype(np.float32)[None]


def make_license(tmp: Path, name="LICENSE.txt") -> Path:
    p = tmp / name
    p.write_text("CC0 1.0 Universal (test fixture text)", encoding="utf-8")
    return p


def make_piano(tmp: Path) -> Path:
    root = tmp / "raw_vcsl_keys"
    (root / "samples").mkdir(parents=True)
    for k in (48, 60, 72):
        for layer, amp in (("p", .3), ("f", 1.0)):
            w = tone(440 * 2 ** ((k - 69) / 12), 3.0) * amp
            write_wav(root / "samples" / f"piano_{k}_{layer}.wav", np.repeat(w, 2, axis=0), SR)
    sfz = ["<control> default_path=samples/", "<group> lovel=0 hivel=63"]
    for k, lo, hi in ((48, 21, 53), (60, 54, 65), (72, 66, 108)):
        sfz.append(f"<region> sample=piano_{k}_p.wav pitch_keycenter={k} lokey={lo} hikey={hi}")
    sfz.append("<group> lovel=64 hivel=127")
    for k, lo, hi in ((48, 21, 53), (60, 54, 65), (72, 66, 108)):
        sfz.append(f"<region> sample=piano_{k}_f.wav pitch_keycenter={k} lokey={lo} hikey={hi}")
    (root / "piano.sfz").write_text("\n".join(sfz), encoding="utf-8")
    return root


def make_bass(tmp: Path) -> Path:
    root = tmp / "raw_bass"
    (root / "s").mkdir(parents=True)
    for k in (30, 40):
        write_wav(root / "s" / f"bass_{k}.wav", tone(440 * 2 ** ((k - 69) / 12), 2.0, decay=.6), SR)
    (root / "bass.sfz").write_text("<control> default_path=s/\n<region> sample=bass_30.wav pitch_keycenter=30 lokey=0 hikey=35\n"
                                   "<region> sample=bass_40.wav pitch_keycenter=40 lokey=36 hikey=127\n", encoding="utf-8")
    return root


def make_kit(tmp: Path) -> Path:
    root = tmp / "raw_kit"
    for i, name in enumerate(["kick_01", "kick_02", "snare_01", "hihat_closed_01", "hihat_open_01", "tom_01", "crash_01"]):
        write_wav(root / f"{name}.wav", np.repeat(noise_hit(.3 if "hat" not in name else .15, i), 2, 0), SR)
    return root


def make_vocalset(tmp: Path, n_female=4, n_male=4) -> Path:
    root = tmp / "raw_vocalset"
    for g, n in (("female", n_female), ("male", n_male)):
        for i in range(1, n + 1):
            for cat in ("scales", "arpeggios", "long_tones", "excerpts"):
                d = root / "data_by_singer" / f"{g}{i}" / cat
                for j in range(2):
                    f = (220 if g == "female" else 130) * (1 + .1 * i)
                    w = tone(f, 4.0 + j, decay=3.0)[0] * (1 + .3 * np.sin(2 * np.pi * 5 * np.arange(int((4 + j) * SR)) / SR))
                    write_wav(d / f"{g[0]}{i}_{cat}_{j}.wav", w[None] * .5, SR)
    return root


def build_factory(tmp: Path, with_vocal=True, with_samples=True, license_ok=True, cfg_over=None) -> Factory:
    """Ingest fixture assets into tmp artifact dirs and return a Factory using them."""
    adir, ldir = tmp / "artifacts_assets", tmp / "artifacts_licenses"
    lic = make_license(tmp)
    cfg = yaml.safe_load((REPO / "configs/data_factory/v0.yaml").read_text())
    cfg["duration_seconds"] = [4.0, 6.0]
    cfg["instruments"], cfg["vocal_index"] = {}, None
    if cfg_over:
        cfg.update(cfg_over)
    records = {k: dict(v) for k, v in A.load_catalog().items()}
    manifests = {}
    if with_samples:
        from data_factory.cli import drumkit_manifest
        from data_factory.sampler import build_manifest_from_sfz
        for aid, root, stem, iid in (("vcsl_keys", make_piano(tmp), "piano", "test_piano"),
                                     ("karoryfer_sneakybass", make_bass(tmp), "bass", "test_bass"),
                                     ("stargate_sample_pack", make_kit(tmp), "drums", "test_kit")):
            rec = A.ingest_asset(aid, root, "test-fixture-1", lic, adir, ldir)
            records[aid] = rec
            if stem == "drums":
                man, _ = drumkit_manifest(root, aid, iid, rec["version"], rec["license"], rec["sha256"])
            else:
                sfz = next(root.glob("*.sfz"))
                man, _ = build_manifest_from_sfz(sfz, root, iid, aid, rec["version"], rec["license"], rec["sha256"])
            mp = tmp / f"{iid}.json"
            mp.write_text(json.dumps(man), encoding="utf-8")
            cfg["instruments"].setdefault(stem, []).append({"manifest": str(mp)})
    vidx = None
    if with_vocal:
        from data_factory.vocal import build_vocal_index
        vroot = make_vocalset(tmp)
        rec = A.ingest_asset("vocalset", vroot, "test-fixture-1", lic, adir, ldir)
        if not license_ok:
            rec["attribution_text"] = ""
        records["vocalset"] = rec
        vidx = build_vocal_index(vroot)
        (tmp / "vocal_index.json").write_text(json.dumps(vidx), encoding="utf-8")
        cfg["vocal_index"] = str(tmp / "vocal_index.json")
    records[A.INTERNAL_ASSET_ID] = A.internal_asset_record()
    cp = tmp / "df.yaml"
    cp.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return Factory.from_yaml(cp, tmp, records=records), cp, records
