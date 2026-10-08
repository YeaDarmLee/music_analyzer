"""Data Factory v0 tests. Fixture assets are procedural (tests/df_fixtures.py); no network, no real asset needed."""
from __future__ import annotations

import copy
import json

import numpy as np
import pytest
import torch

from data_factory import assets as A
from data_factory import composition, performance
from data_factory.adapter import DiskCache, SceneDataset
from data_factory.fixed import render_fixed
from data_factory.fx import PROFILES, apply_chain, random_chain
from data_factory.mixer import mix_stems
from data_factory.qc import qc_scene
from data_factory.sampler import SampleInstrument
from data_factory.scenes import Factory, family_split
from data_factory.schema import NoteEvent
from data_factory.sfz import SfzUnsupported, note_to_midi, parse_sfz, regions_to_zones
from data_factory.synth import DrumSynth, SynthEngine, label_patch, random_kit, random_patch
from data_factory.targets import ATOMIC_ALL, SCHEMAS, build_targets
from data_factory.util import hash_obj, make_rng, sha256_array, tree_sha256
from data_factory.vocal import ALLOWED, build_vocal_index, singer_split
from df_fixtures import build_factory, make_license, make_vocalset

SR = 44100


@pytest.fixture(scope="module")
def fac(tmp_path_factory):
    f, cp, rec = build_factory(tmp_path_factory.mktemp("df"))
    return f


@pytest.fixture(scope="module")
def fac_nosamples(tmp_path_factory):
    f, _, _ = build_factory(tmp_path_factory.mktemp("df2"), with_vocal=False, with_samples=False)
    return f


def sample_rows(f, n=6, split="train"):
    return [f.make_spec(i, split) for i in range(n)]


# --- DF-0 assets / policy --------------------------------------------------------------------------------------
def test_catalog_encodes_packet_verdicts():
    c = A.load_catalog()
    for g in ("vcsl", "vcsl_keys", "vsco2ce", "karoryfer_big_little_bass", "karoryfer_sneakybass", "stargate_sample_pack"):
        assert c[g]["grade"] == "GREEN" and c[g]["license"].startswith("CC0")
    assert c["vocalset"]["grade"] == "GREEN_CONDITIONAL" and c["vocalset"]["attribution_required"] is True
    for r in ("musdb18hq", "medleydb", "moisesdb", "mixing_secrets", "mdb_stem_synth"):
        assert c[r]["grade"] == "RED"
    for y in ("slakh2100", "lakh_midi", "freesound_cc0", "dnr_v3"):
        assert c[y]["grade"] == "YELLOW"


def test_unpinned_catalog_asset_rejected_for_production():
    recs = A.load_records()
    with pytest.raises(A.ManifestError, match="version|sha256"):
        A.gate(recs, ["vcsl_keys"], "PRODUCTION_TRAINING")  # catalog verdict is GREEN but nothing is ingested yet
    A.gate(recs, [A.INTERNAL_ASSET_ID], "PRODUCTION_TRAINING")  # own DSP passes


def test_ingested_cc0_passes_and_license_snapshot_written(tmp_path):
    lic = make_license(tmp_path)
    root = tmp_path / "a"
    root.mkdir()
    (root / "x.wav").write_bytes(b"abc")
    rec = A.ingest_asset("vcsl_keys", root, "v1", lic, tmp_path / "ad", tmp_path / "ld")
    assert (tmp_path / "ld" / "vcsl_keys" / "LICENSE.txt").exists() and rec["license_snapshot_sha256"]
    recs = {**A.load_records(tmp_path / "ad"), "vcsl_keys": rec}
    A.gate(recs, ["vcsl_keys"], "PRODUCTION_TRAINING")
    assert tree_sha256(root)[0] == rec["sha256"] == tree_sha256(root)[0]


def test_attribution_asset_without_text_rejected(tmp_path):
    lic = make_license(tmp_path)
    (tmp_path / "v").mkdir()
    (tmp_path / "v" / "a.wav").write_bytes(b"1")
    rec = A.ingest_asset("vocalset", tmp_path / "v", "v1", lic, tmp_path / "ad", tmp_path / "ld")
    A.gate({"vocalset": rec}, ["vocalset"], "PRODUCTION_TRAINING")
    bad = dict(rec, attribution_text="")
    with pytest.raises(A.ManifestError, match="attribution_text"):
        A.gate({"vocalset": bad}, ["vocalset"], "PRODUCTION_TRAINING")


@pytest.mark.parametrize("aid", ["musdb18hq", "medleydb", "moisesdb", "mixing_secrets", "mdb_stem_synth", "slakh2100",
                                 "lakh_midi", "freesound_cc0", "dnr_v3"])
def test_red_yellow_rejected_for_production(aid):
    recs = A.load_records()
    with pytest.raises(A.ManifestError):
        A.gate(recs, [aid], "PRODUCTION_TRAINING")


def test_red_cannot_be_ingested(tmp_path):
    with pytest.raises(A.ManifestError, match="RED"):
        A.ingest_asset("musdb18hq", tmp_path, "v", make_license(tmp_path), tmp_path / "a", tmp_path / "l")


# --- SFZ / sampler ---------------------------------------------------------------------------------------------------
def test_sfz_parse_inheritance_and_notes():
    txt = "<control> default_path=s/\n<global> volume=-3\n<group> lovel=0 hivel=40\n<region> sample=a b.wav key=c4\n" \
          "<group> lovel=41 hivel=127 loop_mode=loop_continuous loop_start=10 loop_end=900\n<region> sample=c.wav pitch_keycenter=d#3 lokey=40 hikey=50 seq_length=2 seq_position=2 pitch_keytrack=0"
    reg, unsup = parse_sfz(txt)
    zones, _ = regions_to_zones(reg, "sub")
    assert zones[0]["sample"] == "sub/s/a b.wav" and zones[0]["root_key"] == 60 and zones[0]["volume_db"] == -3
    assert zones[1]["root_key"] == 51 and zones[1]["loop"] == [10, 900] and zones[1]["seq"] == [2, 2] and zones[1]["keytrack"] is False
    assert note_to_midi("c#-1") == 1 and note_to_midi("a4") == 69


def test_sfz_critical_opcodes_rejected_not_ignored():
    for bad in ("<region> sample=a.wav sw_last=c1", "<region> sample=a.wav locc64=10", "<region> sample=a.wav xfin_lovel=1",
                "#define $X 1\n<region> sample=a.wav"):
        with pytest.raises(SfzUnsupported):
            parse_sfz(bad)
    reg, unsup = parse_sfz("<region> sample=a.wav sw_last=c1", strict=False)
    assert any("CRITICAL" in k for k in unsup)


def test_sfz_release_triggers_skipped_and_unknown_counted():
    reg, unsup = parse_sfz("<region> sample=a.wav key=60 trigger=release fil_type=lpf_2p\n<region> sample=b.wav key=60")
    zones, notes = regions_to_zones(reg)
    assert len(zones) == 1 and notes["skipped trigger=release"] == 1 and unsup["fil_type"] == 1


def test_sampler_deterministic_and_repitched(fac):
    inst = fac.instruments["test_piano"]
    ev = [NoteEvent("piano", 64, 100, 0.1, 0.8), NoteEvent("piano", 40, 30, 0.5, 1.2)]
    a = inst.render(ev, 3 * SR, make_rng(1))
    b = inst.render(ev, 3 * SR, make_rng(1))
    assert np.array_equal(a, b) and np.abs(a).max() > 0.01
    # a note below the lowest root is pitched down: dominant frequency matches the requested pitch
    one = inst.render([NoteEvent("piano", 57, 100, 0.0, 1.0)], SR, make_rng(1))[0]
    f = np.fft.rfftfreq(len(one), 1 / SR)[np.argmax(np.abs(np.fft.rfft(one * np.hanning(len(one)))))]
    assert abs(f - 220.0) < 8


def test_sampler_velocity_layers_and_release(fac):
    inst = fac.instruments["test_piano"]
    soft = inst.render([NoteEvent("piano", 60, 20, 0, .5)], SR, make_rng(0))
    loud = inst.render([NoteEvent("piano", 60, 120, 0, .5)], SR, make_rng(0))
    assert np.abs(loud).max() > 2 * np.abs(soft).max()
    assert np.abs(loud[:, -50:]).max() < np.abs(loud).max() * 0.2  # released/decayed at the end


# --- synth ---------------------------------------------------------------------------------------------------------------
def test_synth_deterministic_and_labels_from_params():
    ev = [NoteEvent("synth", 60, 100, 0.1, 0.9), NoteEvent("synth", 67, 90, 0.5, 1.4)]
    p = random_patch("pad", make_rng(3))
    a = SynthEngine(p).render(ev, 2 * SR, make_rng(9))
    b = SynthEngine(p).render(ev, 2 * SR, make_rng(9))
    assert np.array_equal(a, b) and np.isfinite(a).all() and np.abs(a).max() > 0.01
    c = SynthEngine(random_patch("pad", make_rng(4))).render(ev, 2 * SR, make_rng(9))
    assert not np.array_equal(a, c)
    pad = {**p, "amp_env": {"a": .5, "d": .5, "s": .8, "r": 1.0}, "sub": 0.0, "noise": 0.0, "fm": None,
           "osc": [{"shape": "saw", "level": 1, "detune_cents": 0, "octave": 0, "pw": .5}]}
    assert label_patch(pad) == "PAD"
    assert label_patch({**pad, "amp_env": {"a": .005, "d": .3, "s": .0, "r": .2}}) == "PLUCK"
    assert label_patch({**pad, "sub": .6, "osc": [{"shape": "saw", "level": 1, "detune_cents": 0, "octave": -1, "pw": .5}]}) == "SYNTH_BASS"
    assert random_patch("pad", make_rng(0))["label_rules_version"] == "labels_v1"


def test_synth_spectrum_is_pitched_and_bandlimited():
    p = {**random_patch("lead", make_rng(1)), "filter": {"type": "lp", "cutoff_hz": 20000.0, "res": .1, "env_amount": 0, "key_track": 0,
         "env": {"a": .01, "d": .1, "s": 1, "r": .1}}, "unison": {"voices": 1, "detune_cents": 0, "spread": 0},
         "lfo": {"rate_hz": 5, "vibrato_cents": 0, "tremolo": 0, "pwm": 0, "filter": 0, "delay_s": 0}}
    p["osc"] = [{"shape": "saw", "level": 1, "detune_cents": 0, "octave": 0, "pw": .5}]
    y = SynthEngine(p).render([NoteEvent("synth", 69, 100, 0, 1.0)], SR, make_rng(0))[0]
    sp = np.abs(np.fft.rfft(y * np.hanning(len(y))))
    assert abs(np.fft.rfftfreq(len(y), 1 / SR)[np.argmax(sp)] - 440) < 5


def test_drum_synth_hits_exist_and_deterministic():
    kit = random_kit(make_rng(2))
    ev = [NoteEvent("drums", k, 100, i * .3, i * .3 + .1) for i, k in enumerate((36, 38, 42, 46, 45, 49))]
    a = DrumSynth(kit).render(ev, 3 * SR, make_rng(1))
    assert np.array_equal(a, DrumSynth(kit).render(ev, 3 * SR, make_rng(1))) and np.abs(a).max() > .05


# --- composition / performance -----------------------------------------------------------------------------------------
def test_composition_and_performance_deterministic():
    c1, c2 = composition.compose(8.0, make_rng(5)), composition.compose(8.0, make_rng(5))
    assert c1 == c2 and c1["family_id"] == c2["family_id"]
    assert composition.compose(8.0, make_rng(6))["family_id"] != c1["family_id"]
    for fn in (performance.piano, performance.bass, performance.drums, performance.synth):
        e1, m1 = fn(c1, 8.0, make_rng(7))
        e2, m2 = fn(c1, 8.0, make_rng(7))
        assert [e.to_list() for e in e1] == [e.to_list() for e in e2] and m1 == m2 and e1
        assert all(0 < e.velocity <= 127 and e.end > e.start >= 0 for e in e1)


def test_performance_patterns_cover_registers():
    c = composition.compose(10.0, make_rng(11))
    b, _ = performance.bass(c, 10.0, make_rng(1))
    assert all(20 <= e.pitch <= 60 for e in b)
    d, _ = performance.drums(c, 10.0, make_rng(1))
    assert {e.pitch for e in d} & {36, 38, 42}


# --- scenes: determinism, variation, exact sum, QC ----------------------------------------------------------------------
def test_same_seed_same_hash_different_seed_varies(fac):
    s1, s2 = fac.make_spec(3, "train"), fac.make_spec(3, "train")
    assert s1.hash() == s2.hash()
    r1, r2 = fac.render(s1), fac.render(s2)
    assert sha256_array(r1["mix"]) == sha256_array(r2["mix"])
    assert all(np.array_equal(r1["atomic"][k], r2["atomic"][k]) for k in ATOMIC_ALL)
    other = fac.make_spec(4, "train")
    assert other.hash() != s1.hash() and sha256_array(fac.render(other)["mix"]) != sha256_array(r1["mix"])


def test_exact_sum_no_clip_inactive_zero_all_scene_types(fac):
    seen = set()
    for i in range(14):
        sp = fac.make_spec(i, "train")
        seen.add(sp.scene_type)
        r = fac.render(sp)
        q = qc_scene(r["mix"], r["atomic"], sp.active_stems, sp.sample_rate, sp.duration_samples)
        assert q.passed, (sp.scene_id, q.failures)
        assert q.stats["mix_sum_max_abs_err"] <= 2e-6 and q.stats["peak"] <= 0.98 + 1e-6
        for s in ATOMIC_ALL:
            if s not in sp.active_stems:
                assert not np.any(r["atomic"][s])
    assert len(seen) >= 3


def test_qc_catches_failures(fac):
    sp = fac.make_spec(0, "train")
    r = fac.render(sp)
    mix, at = r["mix"].copy(), {k: v.copy() for k, v in r["atomic"].items()}
    bad = mix.copy(); bad[0, 5] = np.nan
    assert not qc_scene(bad, at, sp.active_stems, SR, sp.duration_samples).passed
    assert not qc_scene(mix * 20, at, sp.active_stems, SR, sp.duration_samples).passed          # clipping + sum mismatch
    inactive = next(s for s in ATOMIC_ALL if s not in sp.active_stems)
    at2 = {k: v.copy() for k, v in at.items()}; at2[inactive][0, 0] = 1e-3
    assert not qc_scene(mix, at2, sp.active_stems, SR, sp.duration_samples).passed              # non-zero inactive
    assert not qc_scene(mix[:, :-1], at, sp.active_stems, SR, sp.duration_samples).passed       # length
    assert not qc_scene(mix, at, sp.active_stems, 48000, sp.duration_samples).passed            # sample rate
    assert not qc_scene(mix, at, sp.active_stems, SR, sp.duration_samples, manifest_problems=["x"]).passed


def test_mixer_common_gain_keeps_exact_sum_and_limits_peak():
    r = np.random.RandomState(0)
    raw = {"drums": r.randn(2, 4000).astype(np.float32) * 3, "bass": r.randn(2, 4000).astype(np.float32)}
    cfg = {"stem_gain_db": {}, "target_rms_db": 6.0, "peak_limit": 0.9}   # absurdly hot target -> peak guard must engage
    fin, mix, info = mix_stems(raw, {}, cfg, 1, SR, 4000)
    assert info["clip_scale"] < 1 and np.abs(mix).max() <= 0.9 + 1e-6
    assert np.abs(sum(f.astype(np.float64) for f in fin.values()) - mix).max() < 2e-6


def test_fx_silence_stays_silent_and_is_deterministic():
    z = np.zeros((2, 8000), np.float32)
    for prof in PROFILES:
        ch = random_chain("piano", prof, make_rng(3))
        assert not np.any(apply_chain(z, ch, SR, make_rng(1)))
    x = np.random.RandomState(0).randn(2, 8000).astype(np.float32) * .1
    ch = random_chain("synth", "electronic", make_rng(4))
    assert np.array_equal(apply_chain(x, ch, SR, make_rng(2)), apply_chain(x, ch, SR, make_rng(2)))


# --- targets ----------------------------------------------------------------------------------------------------------------
def test_target_hierarchies_2stem_and_future_6stem():
    r = np.random.RandomState(1)
    at = {s: r.randn(2, 100).astype(np.float32) * .01 for s in ("vocal", "drums", "bass", "piano", "synth")}
    two = build_targets(at, "2stem_v1")
    assert np.allclose(two["vocals"], at["vocal"]) and np.allclose(two["instrumental"], at["drums"] + at["bass"] + at["piano"] + at["synth"], atol=1e-6)
    six = build_targets(at, "6stem_v1")
    assert set(six) == {"vocals", "drums", "bass", "guitar", "piano", "rest"} and not np.any(six["guitar"])  # no guitar assets yet
    assert np.allclose(six["rest"], at["synth"], atol=1e-6)
    tot = sum(six.values())
    assert np.allclose(tot, sum(at.values()), atol=1e-6) and np.allclose(sum(two.values()), tot, atol=1e-6)
    for name, g in SCHEMAS.items():
        assert sorted(a for m in g.values() for a in m) == sorted(ATOMIC_ALL), name


# --- splits / leakage -------------------------------------------------------------------------------------------------------
def test_composition_family_split_is_disjoint(fac):
    fams = {s: {fac.make_spec(i, s).composition_family_id for i in range(12)} for s in ("train", "val", "test")}
    assert not (fams["train"] & fams["val"]) and not (fams["train"] & fams["test"]) and not (fams["val"] & fams["test"])
    for s, fs in fams.items():
        assert all(family_split(f, fac.cfg["split_ratios"]) == s for f in fs)


def test_singer_split_disjoint_and_excerpts_excluded(tmp_path):
    idx = build_vocal_index(make_vocalset(tmp_path))
    assert idx["excluded"]["excerpts"] > 0 and all(c["category"] in ALLOWED for c in idx["clips"])
    by = {}
    for c in idx["clips"]:
        by.setdefault(idx["singer_split"][c["singer"]], set()).add(c["singer"])
    assert not (by["train"] & by["val"]) and not (by["train"] & by["test"]) and not (by["val"] & by["test"])
    assert set(by) == {"train", "val", "test"} and idx["publisher_split"] == "NEEDS_RESEARCH"


def test_vocal_clips_per_split_never_cross_singers(fac):
    idx = fac.vocal_index
    for split in ("train", "val", "test"):
        for i in range(8):
            sp = fac.make_spec(i, split)
            if sp.vocal:
                assert idx["singer_split"][sp.vocal["singer"]] == split
                assert sp.vocal["category"] in ALLOWED


def test_singer_split_needs_enough_singers():
    with pytest.raises(ValueError):
        singer_split({"female1": "female", "female2": "female", "male1": "male", "male2": "male", "male3": "male"})


def test_holdout_instruments_only_in_ood(tmp_path):
    f, _, _ = build_factory(tmp_path, cfg_over={"holdout_instruments": ["test_piano"]})
    for i in range(10):
        for split in ("train", "val", "test"):
            r = f.make_spec(i, split).renderers.get("piano", {})
            assert r.get("instrument_id") != "test_piano"
    ood = [f.make_spec(i, "ood").renderers.get("piano", {}) for i in range(10)]
    assert any(r.get("instrument_id") == "test_piano" for r in ood if r)


# --- production gate on scenes ----------------------------------------------------------------------------------------------------
def test_scene_assets_pass_production_gate_and_fallback_is_explicit(fac, fac_nosamples):
    sp = fac.make_spec(0, "train")
    A.gate(fac.records, sp.assets, "PRODUCTION_TRAINING")
    sp2 = fac_nosamples.make_spec(0, "train")
    assert sp2.assets == [A.INTERNAL_ASSET_ID]
    for s, r in sp2.renderers.items():
        assert r["kind"] in ("synth", "drum_synth")
    assert "vocal" not in sp2.active_stems  # no vocal index -> no vocal scenes


def test_vocal_asset_without_attribution_blocks_fixed_render(tmp_path):
    f, _, _ = build_factory(tmp_path, license_ok=False, cfg_over={"scene_types": {"vocal_only": 1.0}})
    rep = render_fixed(f, "train", 2, tmp_path / "out")
    assert len(rep["failed"]) == 2 and "attribution" in json.dumps(rep["failed"])


# --- window rendering / dataset / cache ------------------------------------------------------------------------------------------
def test_window_render_deterministic_and_sized(fac):
    sp = fac.make_spec(1, "train")
    w = (1.0, 1.0 + 131584 / SR)
    a, b = fac.render(sp, w), fac.render(sp, w)
    assert a["mix"].shape == (2, 131584) and sha256_array(a["mix"]) == sha256_array(b["mix"])
    assert np.abs(a["mix"].astype(np.float64) - sum(a["atomic"][s].astype(np.float64) for s in ATOMIC_ALL)).max() < 2e-6


def test_lazy_dataset_items_and_cache(fac, tmp_path):
    cache = DiskCache(tmp_path / "cache", 50_000_000)
    ds = SceneDataset(fac, "train", 4, "2stem_v1", 131584, "lazy", cache=cache)
    a, b = ds[2], ds[2]
    assert a["mix"].shape == (2, 131584) and set(a["stems"]) == {"vocals", "instrumental"} and a["mix"].dtype == torch.float32
    assert torch.equal(a["mix"], b["mix"]) and len(list((tmp_path / "cache").glob("*.npy"))) == 1
    assert torch.allclose(a["stems"]["vocals"] + a["stems"]["instrumental"], a["mix"], atol=2e-6)
    assert not torch.equal(ds[0]["mix"], ds[1]["mix"])


def test_fixed_render_and_dataset(fac, tmp_path):
    rep = render_fixed(fac, "val", 3, tmp_path / "fx")
    assert not rep["failed"] and len(rep["scenes"]) == 3
    d = tmp_path / "fx" / rep["scenes"][0]
    assert {p.name for p in d.iterdir()} >= {"mix.wav", "metadata.json", "provenance.json", "spec.json"}
    prov = json.loads((d / "provenance.json").read_text())
    assert prov["license_manifest_hash"] and A.INTERNAL_ASSET_ID in prov["assets"]
    ds = SceneDataset(fac, "val", 3, "2stem_v1", 131584, "fixed", fixed_dir=tmp_path / "fx")
    it = ds[0]
    assert torch.allclose(it["stems"]["vocals"] + it["stems"]["instrumental"], it["mix"], atol=2e-6)
    ds6 = SceneDataset(fac, "val", 3, "6stem_v1", 131584, "fixed", fixed_dir=tmp_path / "fx")
    assert set(ds6[0]["stems"]) == {"vocals", "drums", "bass", "guitar", "piano", "rest"}


def test_adapter_checks_target_schema_against_model(fac):
    from data_factory.adapter import build
    with pytest.raises(ValueError, match="do not match"):
        build({"params": {"target_schema": "6stem_v1", "factory_config": "x", "num_scenes": {"train": 1}, "chunk_samples": 10}},
              {"stems": ["vocals", "instrumental"]}, "train", 0)


# --- trainer integration -----------------------------------------------------------------------------------------------------------
def _train_steps(fac, device, steps=2):
    import yaml
    from engine.registry import build_model
    from engine.training.trainer import Trainer
    from conftest import CONFIGS
    mc = yaml.safe_load((CONFIGS / "model/our_separator_v01.yaml").read_text())
    tc = yaml.safe_load((CONFIGS / "training/our_v01_poc.yaml").read_text())
    tc.update(device=device, max_steps=steps, grad_accum_steps=2, batch_size=2, val_every=steps, val_batches=1, checkpoint_every=steps,
              amp={"enabled": device == "cuda", "dtype": "float16"}, scheduler=None)
    tr = SceneDataset(fac, "train", 8, "2stem_v1", 131584, "lazy")
    va = SceneDataset(fac, "val", 2, "2stem_v1", 131584, "lazy")
    prov = {"model_id": "our_separator_v01", "model_config_hash": "m", "training_config_hash": "t", "dataset_manifest_sha256": "d",
            "training_run_id": "df-smoke", "git_commit": None, "parent_checkpoint": None}
    import tempfile
    t = Trainer(build_model(mc), tc, tr, va, tempfile.mkdtemp(), prov)
    before = [p.detach().clone() for p in t.model.parameters()]
    val = t.fit()
    assert t.step == steps and all(np.isfinite(v) for v in val.values())
    assert any(not torch.equal(a, b.detach()) for a, b in zip(before, t.model.parameters()))
    return val


def test_our_separator_trains_on_datafactory_scenes_cpu(fac):
    _train_steps(fac, "cpu", steps=1)


@pytest.mark.cuda
@pytest.mark.skipif(not torch.cuda.is_available(), reason="no CUDA device")
def test_our_separator_trains_on_datafactory_scenes_cuda(fac):
    _train_steps(fac, "cuda", steps=2)
