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
        A.gate(recs, ["vsco2ce"], "PRODUCTION_TRAINING")  # catalog verdict is GREEN but not downloaded/ingested (deferred)
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
    assert set(by) == {"train", "val", "test"} and "NEEDS_RESEARCH" in idx["publisher_split"]


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
    core = ["val_loss", "val_sdr", "val_si_sdr", "val_reconstruction_error_db"]  # grouped/per-stem detail may be NaN (no active item)
    assert t.step == steps and all(np.isfinite(val[k]) for k in core)
    assert any(not torch.equal(a, b.detach()) for a, b in zip(before, t.model.parameters()))
    return val


def test_our_separator_trains_on_datafactory_scenes_cpu(fac):
    _train_steps(fac, "cpu", steps=1)


@pytest.mark.cuda
@pytest.mark.skipif(not torch.cuda.is_available(), reason="no CUDA device")
def test_our_separator_trains_on_datafactory_scenes_cuda(fac):
    _train_steps(fac, "cuda", steps=2)


# --- training path = full render + crop (property) / activity metadata ---------------------------------------------------------
@pytest.mark.parametrize("use_cache", [False, True])
def test_training_crop_equals_slice_of_full_render(fac, tmp_path, use_cache):
    from data_factory.adapter import crop_start_samples
    cache = DiskCache(tmp_path / "c", 10**9) if use_cache else None
    ds = SceneDataset(fac, "train", 6, "2stem_v1", 131584, "lazy", cache=cache)
    for rounds in range(2 if use_cache else 1):  # second round reads the cache
        for i in range(6):
            sp = ds.spec(i)
            start = crop_start_samples(sp.seeds["mix"], sp.duration_samples, 131584)
            r = fac.render(sp)
            ref_mix = r["mix"][:, start:start + 131584]
            ref_t = {k: v[:, start:start + 131584] for k, v in build_targets(r["atomic"], "2stem_v1").items()}
            it = ds[i]
            assert np.allclose(it["mix"].numpy(), ref_mix, atol=1e-6, rtol=0)
            for k in ref_t:
                assert np.allclose(it["stems"][k].numpy(), ref_t[k], atol=1e-6, rtol=0)


def test_window_render_path_is_not_the_full_render(fac):
    """Documents why 'window' is experimental: it differs from the full render (scene-level gain, long-note carry)."""
    sp = next(s for s in sample_rows(fac, 8) if "synth" in s.active_stems)
    start, n = 1.5, 88200
    full = fac.render(sp)["mix"][:, int(start * SR):int(start * SR) + n]
    win = fac.render(sp, (start, start + n / SR))["mix"]
    assert not np.allclose(full, win, atol=1e-4)


def test_item_activity_flags_follow_the_data(fac):
    ds = SceneDataset(fac, "train", 40, "2stem_v1", 131584, "lazy")
    seen = set()
    for i in range(40):
        it = ds[i]
        for k, v in it["stems"].items():
            flag = bool(it["active"][k])
            assert flag == bool(v.abs().max() > 1e-4)
            seen.add((k, flag))
    assert seen == {("vocals", True), ("vocals", False), ("instrumental", True), ("instrumental", False)}


# --- DF-0 ingest features -----------------------------------------------------------------------------------------------------
def test_sfz_cc_state_gating_is_region_selection_not_ignoring():
    txt = ("<group> locc64=65 hicc64=127\n<region> sample=sus.wav key=60\n"
           "<group> locc64=0 hicc64=64\n<region> sample=nosus.wav key=60\n"
           "<group> on_locc64=64 on_hicc64=127\n<region> sample=pedal_down_thump.wav key=60\n"
           "<group> locc99=10\n<region> sample=other.wav key=61")
    with pytest.raises(SfzUnsupported):
        parse_sfz(txt)                                    # CC gates are critical without an explicit state
    with pytest.raises(SfzUnsupported):
        parse_sfz(txt, cc_state={64: 127})                # cc99 is still undefined -> still critical
    reg, uns = parse_sfz(txt.split("<group> locc99")[0], cc_state={64: 127})
    assert [r["sample"] for r in reg] == ["sus.wav"]
    assert uns["dropped region: CC-triggered (on_loccN)"] == 1 and any("outside cc_state" in k for k in uns)


def test_build_manifest_records_overrides_and_resolves_relative_samples(tmp_path):
    from data_factory.sampler import build_manifest_from_sfz
    from data_factory.util import write_wav
    root = tmp_path / "a"
    (root / "Programs" / "maps").mkdir(parents=True)
    (root / "Samples").mkdir()
    write_wav(root / "Samples" / "x.wav", np.zeros((2, 100), np.float32), SR)
    (root / "Programs" / "maps" / "m.sfz").write_text("<region>\nsample=..\\Samples\\x.wav\nlokey=30 hikey=40 pitch_keycenter=35\n")
    man, rep = build_manifest_from_sfz([(root / "Programs" / "maps" / "m.sfz", {"hivel": 63, "seq_length": 5})], root, "i", "karoryfer_sneakybass",
                                       "v", "CC0-1.0", "sha", base_dir="Programs")
    z = man["zones"][0]
    assert z["sample"] == "Samples/x.wav" and z["hi_vel"] == 63 and z["seq"] == [1, 5] and rep["missing_samples"] == []
    assert man["ingest_overrides"] == {"Programs/maps/m.sfz": {"hivel": 63, "seq_length": 5}}


def test_drumkit_roles_velocity_layers_and_filters(tmp_path):
    from data_factory.cli import drumkit_manifest
    from data_factory.util import write_wav
    names = ["Snare Drum/Snare2_HitSN_v2_rr1.wav", "Snare Drum/Snare2_HitSN_v4_rr1.wav", "Snare Drum/Snare2_HitNS_v2_rr1.wav",
             "Snare Drum/Snare2_rollSN_v2.wav", "Hi-Hat/HiHat_HitC_v1_rr1.wav", "Hi-Hat/HiHat_HitO_v1_rr1.wav", "Hi-Hat/HiHat_HitOC_v1_rr1.wav",
             "Bass Drum 1/BDrumNew_hit_v1.wav", "freesound/kick/k.wav", "Tom 1/Stick/TomH_HitS_v1_rr1.wav", "Tom 1/TomH_rimS_v1.wav"]
    for n in names:
        write_wav(tmp_path / n, np.zeros((2, 50), np.float32), SR)
    man, rep = drumkit_manifest(tmp_path, "vcsl", "k", "v", "CC0-1.0", "sha", exclude_prefixes=("freesound/",),
                                name_include="hit", name_exclude="roll|rim|hitns")
    assert rep["roles"] == {"snare": 2, "hat_closed": 1, "hat_open": 2, "kick": 1, "tom": 1} or rep["roles"]["snare"] == 2
    assert rep["roles"]["kick"] == 1 and rep["excluded_files"] >= 3
    snares = sorted((z["lo_vel"], z["hi_vel"]) for z in man["zones"] if z["root_key"] == 38)
    assert snares == [(1, 63), (64, 127)]                         # two velocity layers split the range
    inst = SampleInstrument(man, tmp_path, SR)
    z = inst.select_zone(38, 120, 0.5, 0)
    assert "v4" in z["sample"]


def test_forced_scene_content_and_samples(fac):
    sp = fac.make_spec(0, "val", force={"active": ["piano"], "sample": True, "scene_type": "listen_piano"})
    assert sp.active_stems == ["piano"] and sp.renderers["piano"]["kind"] == "sample" and sp.scene_type == "listen_piano"
    sp2 = fac.make_spec(0, "val", force={"active": ["drums", "bass"], "sample": True})
    assert sp2.renderers["drums"]["kind"] == "sample" and sp2.renderers["bass"]["kind"] == "sample"
    assert fac.make_spec(0, "val").hash() != sp.hash()


def test_read_wav_head_only_matches_full_prefix(tmp_path):
    from data_factory.util import read_wav, write_wav
    x = np.random.RandomState(0).randn(2, 44100 * 2).astype(np.float32) * .1
    write_wav(tmp_path / "a.wav", x, SR)
    head, _ = read_wav(tmp_path / "a.wav", None, 0.5)
    assert head.shape == (2, 22050) and np.array_equal(head, x[:, :22050])


def test_publisher_test_singers_become_test_split(tmp_path):
    root = make_vocalset(tmp_path)
    (root / "test_singers_technique.txt").write_text("female2" + chr(10) + "male3" + chr(10), encoding="utf-8")
    idx = build_vocal_index(root)
    sp = idx["singer_split"]
    assert sp["female2"] == "test" and sp["male3"] == "test"
    assert sp["female4"] == "val" and sp["male4"] == "val"                 # highest-numbered remaining singer per gender
    assert sorted(set(sp.values())) == ["test", "train", "val"] and "used:" in idx["publisher_split"]
    assert all(sp[s] == "train" for s in ("female1", "female3", "male1", "male2"))


def test_stem_reference_loudness_equalizes_before_random_gains():
    from data_factory.mixer import active_rms
    r = np.random.RandomState(0)
    quiet = (r.randn(2, 20000) * 0.002).astype(np.float32)
    loud = (r.randn(2, 20000) * 0.2).astype(np.float32)
    loud[:, 10000:] = 0  # half silence must not dilute the loudness estimate
    cfg = {"stem_gain_db": {}, "target_rms_db": -20.0, "peak_limit": 0.98, "stem_ref_rms_db": -20.0}
    fin, mix, _ = mix_stems({"vocal": quiet, "drums": loud}, {}, cfg, 1, SR, 20000)
    assert abs(20 * np.log10(active_rms(fin["vocal"])) - 20 * np.log10(active_rms(fin["drums"]))) < 0.5
    assert np.abs(sum(f.astype(np.float64) for f in fin.values()) - mix).max() < 2e-6


# ---- DF-0 follow-up: pedal states, amp_veltrack/global_volume, fixed-key composition, multi-phrase vocal --------------------
PEDAL_SFZ = """<global> global_volume=3 amp_veltrack=80
<group> locc64=65 hicc64=127
<region> sample=sus.wav key=60
<group> locc64=0 hicc64=64
<region> sample=nosus.wav key=60
"""


def test_sfz_pedal_states_veltrack_global_volume():
    down, _ = parse_sfz(PEDAL_SFZ, cc_state={64: 127})
    up, _ = parse_sfz(PEDAL_SFZ, cc_state={64: 0})
    assert [r["sample"] for r in down] == ["sus.wav"] and [r["sample"] for r in up] == ["nosus.wav"]
    z = regions_to_zones(down, ".")[0][0]
    assert z["volume_db"] == 3.0 and z["amp_veltrack"] == 80.0


def test_sampler_pedal_region_set_and_veltrack(fac):
    inst = next(iter(fac.instruments.values()))
    zd = dict(inst.zones[0], lo_key=0, hi_key=127, lo_vel=0, hi_vel=127)
    zu = dict(zd, sample=zd["sample"] + ".up")
    saved = inst.zones, inst.zones_pedal_up  # module-scoped fixture: restore afterwards
    inst.zones, inst.zones_pedal_up = [zd], [zu]
    try:
        assert inst.select_zone(60, 80, 0.1, 0, pedal_down=True)["sample"] == zd["sample"]
        assert inst.select_zone(60, 80, 0.1, 0, pedal_down=False)["sample"] == zu["sample"]
    finally:
        inst.zones, inst.zones_pedal_up = saved
    zv = dict(zd, amp_veltrack=100.0, volume_db=0.0, tune_cents=0.0, root_key=60, keytrack=True)
    loud, soft = (np.abs(inst._note(zv, 60, v, 2000)).max() for v in (127, 32))
    assert 10 < loud / soft < 20  # veltrack 100% with v^2 curve: (127/32)^2 = 15.7


def test_piano_pedal_mode_varies_and_events_carry_cc64():
    modes, cc = set(), set()
    for i in range(30):
        rng = make_rng(i)
        c = composition.compose(8.0, rng)
        ev, meta = performance.piano(c, 8.0, rng)
        modes.add(meta["pedal_mode"])
        cc |= {e.meta["cc64"] for e in ev}
    assert modes == {"up", "down", "mixed"} and cc == {0, 127}


def test_compose_fixed_overrides_without_shifting_rng_stream():
    r1, r2 = make_rng(5), make_rng(5)
    a = composition.compose(10.0, r1)
    b = composition.compose(10.0, r2, fixed={"bpm": 100, "key_root": 3, "mode": "minor", "n_bars": 6})
    assert (b["bpm"], b["key_root"], b["mode"], b["n_bars"]) == (100, 3, "minor", 6)
    assert r1.rand() != r2.rand() or len(a["chords"]) != len(b["chords"])  # different bar count -> different chord draws
    # draw count of the header fields is identical: same section type draw
    r3, r4 = make_rng(9), make_rng(9)
    assert composition.compose(10.0, r3)["section_type"] == composition.compose(10.0, r4, fixed={"bpm": 99})["section_type"]


def test_vocal_len_s_truncates_with_fade(tmp_path):
    from data_factory.vocal import render_vocal
    import scipy.io.wavfile as wf
    wf.write(str(tmp_path / "c.wav"), 44100, (np.sin(np.arange(44100 * 3) * 0.05) * 0.5).astype(np.float32))
    spec = {"clip_id": "c.wav", "crop_start_s": 0.0, "place_start_s": 0.5, "len_s": 1.0, "silence": [], "double": None}
    y = render_vocal(spec, tmp_path, 44100 * 3, 44100)
    assert np.abs(y[:, int(1.55 * 44100):]).max() == 0 and np.abs(y[:, int(1.4 * 44100):int(1.45 * 44100)]).max() > 0


# ---- persistent full-scene cache + per-epoch crops + validation detail ------------------------------------------------------
def test_scene_cache_crop_exact_and_epoch_variation(fac, tmp_path):
    from data_factory.adapter import SceneCache, crop_start_samples
    sc = SceneCache(tmp_path / "sc")
    ds = SceneDataset(fac, "train", 6, "2stem_v1", 131584, "lazy", scene_cache=sc)
    ref = SceneDataset(fac, "train", 6, "2stem_v1", 131584, "lazy")  # uncached full-render path
    starts = {}
    for epoch in (0, 1, 2):
        ds.set_epoch(epoch)
        ref.set_epoch(epoch)
        for i in range(6):
            a, b = ds[i], ref[i]  # epoch 0: miss (render+store); later epochs: hit (mmap crop of the same cached scene)
            assert bool(a["telemetry"]["hit"]) == (epoch > 0)
            assert torch.equal(a["mix"], b["mix"]) and all(torch.equal(a["stems"][k], b["stems"][k]) for k in a["stems"])
            assert a["active"].keys() == b["active"].keys() and all(bool(a["active"][k]) == bool(b["active"][k]) for k in a["active"])
            sp = ds.spec(i)
            starts.setdefault(i, set()).add(crop_start_samples(sp.seeds["mix"] + epoch, sp.duration_samples, 131584))
    assert sum(len(v) > 1 for v in starts.values()) >= 4  # scenes longer than the chunk get a different window each epoch
    ds.set_epoch(1)
    assert torch.equal(ds[2]["mix"], ds[2]["mix"])  # same epoch -> same crop (reproducible)
    assert len(list((tmp_path / "sc").rglob("*.npy"))) == 6  # one entry per scene, independent of crop/epoch


def test_scene_cache_key_ignores_crop_and_follows_content(fac, tmp_path):
    from data_factory.adapter import SceneCache
    ds = SceneDataset(fac, "train", 2, "2stem_v1", 131584, "lazy", scene_cache=SceneCache(tmp_path / "k"))
    sp = ds.spec(0)
    k0 = ds.cache_key(sp)
    ds.set_epoch(5)
    assert ds.cache_key(sp) == k0 and ds.cache_key(ds.spec(1)) != k0
    inst = next(iter(fac.instruments.values()))
    old = inst.m["zones"][0]["volume_db"]
    try:
        inst.m["zones"][0]["volume_db"] = old + 1.0  # an asset/instrument change must invalidate every cached scene
        ds2 = SceneDataset(fac, "train", 2, "2stem_v1", 131584, "lazy", scene_cache=SceneCache(tmp_path / "k"))
        assert ds2.cache_key(sp) != k0
    finally:
        inst.m["zones"][0]["volume_db"] = old


def test_val_aggregator_groups_and_active_only():
    from engine.interfaces import SeparationOutput
    from engine.training.metrics import ValAggregator
    t = torch.randn(2, 2, 4000)
    tgt = {"vocals": t.clone(), "instrumental": torch.zeros(2, 2, 4000)}
    est = SeparationOutput({"vocals": t.clone() + 0.01 * torch.randn_like(t), "instrumental": torch.zeros(2, 2, 4000) + 1e-4}, 44100, {})
    agg = ValAggregator()
    agg.add(est, tgt, t.clone(), {"vocals": torch.tensor([True, True]), "instrumental": torch.tensor([False, False])},
            {"category": ["a", "b"], "singer": ["s1", ""]})
    s = agg.summary()
    assert s["val_si_sdr_vocals"] > 20 and s["val_n_active_instrumental"] == 0 and s["val_si_sdr_instrumental"] != s["val_si_sdr_instrumental"]
    assert s["val_category/a/n"] == 1 and s["val_singer/s1/n"] == 1 and "val_singer/" not in "".join(k for k in s if k.endswith("/n") and "/ /" in k)
    assert s["val_category/a/inactive_rms_db"] < -20
