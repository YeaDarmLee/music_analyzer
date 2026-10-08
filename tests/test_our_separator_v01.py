"""OurSeparatorV01 tests. Small configs keep CPU tests fast; the full Packet-02 spec is built once for count/shape checks."""
from __future__ import annotations

import copy
from pathlib import Path

import numpy as np
import pytest
import torch
import yaml

from engine.checkpoint import load_checkpoint, save_checkpoint
from engine.inference import separate
from engine.models.our_separator_v01.band_map import bands_per_bin, build_band_slices
from engine.models.our_separator_v01.heads import MixtureProjection
from engine.registry import LOSSES, MODELS, build_model

FULL = yaml.safe_load((Path(__file__).resolve().parents[1] / "configs/model/our_separator_v01.yaml").read_text())


def small(**over):
    c = copy.deepcopy(FULL)
    c["sample_rate"] = 8000
    c["params"].update(n_fft=256, hop_length=64, win_length=256, num_bands=12, dim=32, depth=2, heads=2, dim_head=16,
                       decoder_hidden=64, gradient_checkpointing=False)
    c["params"].update(over)
    return c


def audio(b=2, t=2000, seed=0):
    return torch.randn(b, 2, t, generator=torch.Generator().manual_seed(seed)) * 0.1


def perturb_outputs(m):  # zero-init output layers give zero grads upstream at step 0; make them non-zero for grad tests
    for p in m.out_proj.parameters():
        torch.nn.init.normal_(p, std=0.02)


# --- spec facts ------------------------------------------------------------------------------------------------
def test_registered_and_spec_values():
    assert "our_separator_v01" in MODELS.names()
    p = FULL["params"]
    assert (FULL["sample_rate"], p["n_fft"], p["hop_length"], p["num_bands"], p["dim"], p["depth"], p["heads"],
            p["dim_head"], p["ff_expansion"]) == (44100, 2048, 512, 60, 192, 6, 6, 32, 2)
    assert 131584 % 512 == 0 and abs(131584 / 44100 - 2.9838) < 1e-4


def test_full_spec_param_count_within_budget():
    m = build_model(FULL)
    bd = m.parameter_breakdown()
    assert 8e6 <= bd["total"] <= 12e6 and bd["total"] <= 15e6  # Packet 02 target and hard gate
    assert bd["total"] == sum(bd[k] for k in ("band_projector", "backbone", "decoder_trunk", "output_projection"))


def test_band_map_covers_all_bins_with_overlap():
    sl = build_band_slices(44100, 2048, 60)
    cnt = bands_per_bin(sl, 1025)
    assert len(sl) == 60 and cnt.min() >= 1 and cnt[0] >= 1 and cnt[-1] >= 1 and cnt.max() >= 2
    assert all(a[0] <= b[0] and a[1] <= b[1] for a, b in zip(sl, sl[1:]))
    assert build_band_slices(44100, 2048, 60) == sl  # deterministic
    with pytest.raises(AssertionError):
        assert build_band_slices(44100, 2048, 59) == sl


# --- shapes / lengths ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("t", [2000, 2001, 1999, 777])
def test_shapes_even_odd_lengths(t):
    m = build_model(small()).eval()
    x = audio(t=t)
    with torch.no_grad():
        o = m(x)
    assert list(o.stems) == ["vocals", "instrumental"]
    for v in o.stems.values():
        assert v.shape == x.shape and torch.isfinite(v).all()
    assert o.sample_rate == 8000 and o.aux["input_scale"].shape == (2, 1, 1)


def test_full_spec_forward_shape_cpu():
    m = build_model(FULL).eval()
    x = audio(b=1, t=131584)
    with torch.no_grad():
        o = m(x)
    assert o.stems["vocals"].shape == (1, 2, 131584)
    assert (x - sum(o.stems.values())).abs().max() < 1e-5


# --- mixture consistency ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("mode", ["project", "residual"])
def test_sum_equals_mix_after_training_like_perturbation(mode):
    m = build_model(small(output_consistency_mode=mode)).eval()
    perturb_outputs(m)
    x = audio()
    with torch.no_grad():
        o = m(x)
    assert (x - sum(o.stems.values())).abs().max() < 1e-5


def test_soft_mode_does_not_enforce_sum():
    m = build_model(small(output_consistency_mode="soft")).eval()
    perturb_outputs(m)
    x = audio()
    with torch.no_grad():
        o = m(x)
    assert (x - sum(o.stems.values())).abs().max() > 1e-3
    assert LOSSES.get("mixture_l1")(o, {}, x).item() > 0


def test_residual_mode_predicts_one_fewer_stem():
    m = build_model(small(output_consistency_mode="residual"))
    assert m.num_predicted == 1
    assert build_model(small(output_consistency_mode="project")).num_predicted == 2


def test_projection_generalizes_to_n_stems():
    proj = MixtureProjection("project")
    mix, est = torch.randn(2, 2, 100), torch.randn(2, 6, 2, 100)
    assert torch.allclose(proj(mix, est).sum(1), mix, atol=1e-5)


def test_stem_count_comes_from_config_only():
    c = small()
    c["stems"] = ["vocals", "drums", "bass", "guitar", "piano", "rest"]
    m = build_model(c).eval()
    with torch.no_grad():
        o = m(audio())
    assert len(o.stems) == 6 and (audio() - sum(o.stems.values())).abs().max() < 1e-5


def test_initial_state_is_zero_mask_split():
    m = build_model(small()).eval()
    x = audio()
    with torch.no_grad():
        o = m(x)
    assert torch.allclose(o.stems["vocals"], x / 2, atol=1e-5) and torch.allclose(o.stems["instrumental"], x / 2, atol=1e-5)


# --- normalization --------------------------------------------------------------------------------------------------
def test_input_normalization_scale_equivariance():
    m = build_model(small()).eval()
    perturb_outputs(m)
    x = audio()
    with torch.no_grad():
        a, b = m(x), m(x * 10)
    for k in a.stems:
        assert torch.allclose(a.stems[k] * 10, b.stems[k], atol=1e-4)
    assert torch.allclose(b.aux["input_scale"], a.aux["input_scale"] * 10, rtol=1e-4)


def test_normalization_off_gives_unit_scale():
    m = build_model(small(input_normalization=False)).eval()
    with torch.no_grad():
        assert torch.all(m(audio()).aux["input_scale"] == 1)


# --- gradients -----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("ckpt", [False, True])
def test_gradients_reach_every_module(ckpt):
    m = build_model(small(gradient_checkpointing=ckpt)).train()
    perturb_outputs(m)
    o = m(audio(b=1))
    tgt = torch.randn_like(o.stems["vocals"])
    loss = ((o.stems["vocals"] - tgt) ** 2).mean() + ((o.stems["instrumental"] + tgt) ** 2).mean()
    loss.backward()
    groups = {"band_proj": m.band_proj, "time_attn": [b.attn_t for b in m.blocks], "freq_attn": [b.attn_f for b in m.blocks],
              "ffn": [x for b in m.blocks for x in (b.ff_t, b.ff_f)], "decoder": m.decoder_trunk, "out": m.out_proj}
    for name, mods in groups.items():
        mods = mods if isinstance(mods, (list, torch.nn.ModuleList)) else [mods]
        ps = [p for mod in mods for p in mod.parameters()]
        assert all(p.grad is not None and torch.isfinite(p.grad).all() for p in ps), name
        assert any(p.grad.abs().sum() > 0 for p in ps), name


def test_checkpointing_does_not_change_gradients():
    gs = []
    for ck in (False, True):
        torch.manual_seed(0)
        m = build_model(small(gradient_checkpointing=ck)).train()
        perturb_outputs(m) if False else None
        torch.manual_seed(1)
        perturb_outputs(m)
        o = m(audio(b=1))
        (o.stems["vocals"] ** 2).mean().backward()
        gs.append(torch.cat([p.grad.flatten() for p in m.blocks.parameters()]))
    assert torch.allclose(gs[0], gs[1], atol=1e-6)


# --- losses -------------------------------------------------------------------------------------------------------------------
def test_new_losses_finite_and_scale_aware():
    m = build_model(small()).eval()
    x = audio()
    tgt = {"vocals": x * 0.5, "instrumental": x * 0.5}
    with torch.no_grad():
        o = m(x)
    res = [[256, 64, 256], [128, 32, 128]]
    for name, kw in [("waveform_l1", {}), ("multires_stft", {"resolutions": res}), ("si_sdr", {}), ("mixture_l1", {})]:
        v = LOSSES.get(name)(o, tgt, x, **kw)
        assert torch.isfinite(v), name
    # perfect prediction -> ~0 stft loss
    o.stems = {k: v.clone() for k, v in tgt.items()}
    assert LOSSES.get("multires_stft")(o, tgt, x, resolutions=res).item() < 1e-3


# --- checkpoint / state ----------------------------------------------------------------------------------------------------------
def test_band_layout_mismatch_rejected_on_load(tmp_path):
    a, b = build_model(small()), build_model(small(num_bands=10))
    with pytest.raises(ValueError, match="band layout"):
        b.load_state_dict(a.state_dict())


def test_checkpoint_roundtrip_same_output(tmp_path):
    m = build_model(small()).eval()
    perturb_outputs(m)
    prov = {"model_id": "our_separator_v01", "model_config_hash": "m", "training_config_hash": "t",
            "dataset_manifest_sha256": "d", "training_run_id": "r", "git_commit": None, "parent_checkpoint": None}
    save_checkpoint(tmp_path / "a.ckpt", {"model": m.state_dict()}, prov)
    state, _ = load_checkpoint(tmp_path / "a.ckpt")
    m2 = build_model(small()).eval()
    m2.load_state_dict(state["model"])
    x = audio()
    with torch.no_grad():
        assert torch.equal(m(x).stems["vocals"], m2(x).stems["vocals"])


def test_chunked_inference_runs_with_overlap():
    m = build_model(small()).eval()
    perturb_outputs(m)
    x = audio(b=1, t=5000)[0]
    o = separate(m, x, chunk_samples=2048, overlap_samples=1024)
    assert o.stems["vocals"].shape == x.shape and torch.isfinite(o.stems["vocals"]).all()
    assert (x - sum(o.stems.values())).abs().max() < 1e-4  # overlap-add of projected chunks still sums to the mix


# --- AMP (cuda) ----------------------------------------------------------------------------------------------------------------------
@pytest.mark.cuda
@pytest.mark.skipif(not torch.cuda.is_available(), reason="no CUDA device")
def test_cuda_amp_fp16_forward_backward_full_spec():
    m = build_model(FULL).cuda().train()
    perturb_outputs(m)
    x = audio(b=1, t=131584).cuda()
    with torch.autocast("cuda", dtype=torch.float16):
        o = m(x)
        loss = LOSSES.get("waveform_l1")(o, {"vocals": x * 0.5, "instrumental": x * 0.5}, x)
    loss.backward()
    assert torch.isfinite(loss) and all(torch.isfinite(p.grad).all() for p in m.parameters() if p.grad is not None)
    assert (x - sum(o.stems.values())).abs().max() < 1e-3  # fp16 tolerance


def test_multires_stft_silent_target_explodes_without_floor_and_is_bounded_with_it():
    """Inactive stems (exactly silent targets) are normal in Data Factory scenes."""
    x = audio(b=1, t=4000)
    sil = torch.zeros_like(x)
    from engine.interfaces import SeparationOutput
    out = SeparationOutput({"vocals": x / 2, "instrumental": x / 2}, 8000, aux={"input_scale": x.pow(2).mean().sqrt().view(1, 1, 1)})
    tg = {"vocals": sil, "instrumental": x}
    res = [[256, 64, 256]]
    plain = LOSSES.get("multires_stft")(out, tg, x, resolutions=res)
    floored = LOSSES.get("multires_stft")(out, tg, x, resolutions=res, sc_floor_rel=0.01)
    assert plain.item() > 1e6 and torch.isfinite(floored) and floored.item() < 200
    ok = {"vocals": x / 2, "instrumental": x / 2}
    assert LOSSES.get("multires_stft")(out, ok, x, resolutions=res, sc_floor_rel=0.01).item() < 1e-3  # perfect prediction stays ~0


def _act_out(x, sc=None):
    from engine.interfaces import SeparationOutput
    return SeparationOutput({"vocals": x / 2, "instrumental": x / 2}, 8000, aux={"input_scale": x.pow(2).mean(dim=(1, 2), keepdim=True).sqrt()})


def test_multires_stft_activity_aware_inactive_target_is_bounded_and_skips_convergence():
    x = audio(b=2, t=4000)
    out = _act_out(x)
    res = [[256, 64, 256]]
    tg = {"vocals": torch.zeros_like(x), "instrumental": x}
    act = {"vocals": torch.tensor([False, False]), "instrumental": torch.tensor([True, True])}
    fn = LOSSES.get("multires_stft")
    v = fn(out, tg, x, resolutions=res, active=act)
    assert torch.isfinite(v) and v.item() < 50
    # no activity info and no floor -> the Packet-02 form explodes on this input
    assert fn(out, tg, x, resolutions=res).item() > 1e6
    # gradients through masked (silent) rows are finite, not NaN
    p = x.clone().requires_grad_(True)
    o2 = _act_out(x)
    o2.stems = {"vocals": p / 2, "instrumental": x / 2}
    fn(o2, tg, x, resolutions=res, active=act).backward()
    assert torch.isfinite(p.grad).all()
    # inactive items contribute only the linear magnitude term: silent output is a zero-loss optimum
    o3 = _act_out(x)
    o3.stems = {"vocals": torch.zeros_like(x), "instrumental": x}
    assert fn(o3, {"vocals": torch.zeros_like(x), "instrumental": x}, x, resolutions=res, active=act).item() < 1e-6


def test_multires_stft_all_active_matches_per_item_form_and_mixed_batch():
    x = audio(b=2, t=4000)
    out = _act_out(x)
    res = [[256, 64, 256]]
    tg = {"vocals": x * 0.3, "instrumental": x * 0.7}
    fn = LOSSES.get("multires_stft")
    all_act = {k: torch.tensor([True, True]) for k in tg}
    a = fn(out, tg, x, resolutions=res, active=all_act)
    b = fn(out, tg, x, resolutions=res, sc_floor_rel=1e-9)  # per-item path without activity
    assert torch.allclose(a, b, rtol=1e-4)
    mixed = {"vocals": torch.tensor([True, False]), "instrumental": torch.tensor([True, True])}
    tg2 = {"vocals": torch.stack([x[0] * 0.3, torch.zeros_like(x[1])]), "instrumental": x * 0.7}
    assert torch.isfinite(fn(out, tg2, x, resolutions=res, active=mixed))


def test_composite_passes_activity_to_losses():
    from engine.training.losses import build_composite
    x = audio(b=1, t=4000)
    out = _act_out(x)
    comp = build_composite([{"name": "multires_stft", "weight": 1.0, "kwargs": {"resolutions": [[256, 64, 256]]}}])
    tg = {"vocals": torch.zeros_like(x), "instrumental": x}
    total, _ = comp(out, tg, x, {"vocals": torch.tensor([False]), "instrumental": torch.tensor([True])})
    assert torch.isfinite(total) and total.item() < 50
