"""Production preset isolation: release profile, allowlist, fail-closed gate, CLAPSep exclusion, notice cross-checks."""
import ast
import json
import sys
import types
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from music_analyzer import license_notices, registry, release
from music_analyzer.common import read_json, write_json
from music_analyzer.legal import RIGHTS_CONFIRMATION_VERSION
from test_legal_trust import served, stored_analysis  # noqa: F401  (fixtures/helpers shared with the legal suite)

SRC = Path(release.__file__).parent
DEV_PRESETS = ["basic_2", "basic_6", "final_11", "final_10", "instrument_roformer_6s", "quality_6s"]


def upload(preset):
    return f"/api/analyses?preset={preset}&rights={RIGHTS_CONFIRMATION_VERSION}"


def approvals_for(models, **override):
    entries = {m: {"status": "APPROVED", "checkpoint_sha256": registry.config(m)["upstream_sha256_prefix"],
                   "evidence_url": f"https://example.invalid/{m}", "basis": "test"} for m in models}
    for model, change in override.items():
        entries[model] = {**entries[model], **change}
    return {"models": entries}


@pytest.fixture
def commercial(served, tmp_path, monkeypatch):
    """Commercial profile with commercial_13 promoted to APPROVED in a throwaway config and approval file."""
    request, library, store = served
    config = read_json(release.CONFIG)
    config["commercial"]["presets"] = {name: {"status": "APPROVED" if name == "commercial_13" else "VALIDATING"} for name in config["commercial"]["presets"]}
    path = tmp_path / "release_presets.json"
    write_json(path, config)
    monkeypatch.setattr(release, "CONFIG", path)
    monkeypatch.setenv("MUSIC_RELEASE_PROFILE", "commercial")
    models = release.model_ids_for("commercial_13")

    def approve(**override):
        document = approvals_for(models, **override)
        write_json(tmp_path / "approval.json", document)
        monkeypatch.setattr(registry, "APPROVAL", tmp_path / "approval.json")
        for model, entry in document["models"].items():
            registration = library.root / "models" / model / "registration.json"
            registration.parent.mkdir(parents=True, exist_ok=True)
            write_json(registration, {"checkpoint_sha256": entry["checkpoint_sha256"]})
        return document

    approve()
    return types.SimpleNamespace(request=request, library=library, store=store, models=models, approve=approve, config=path, tmp=tmp_path)


# --- profile -------------------------------------------------------------------------------------------

def test_profile_defaults_to_development_and_rejects_unknown_values(monkeypatch):
    monkeypatch.delenv("MUSIC_RELEASE_PROFILE", raising=False)
    assert release.profile({}) == "development"
    assert release.profile({"MUSIC_RELEASE_PROFILE": " Commercial "}) == "commercial"
    with pytest.raises(release.ReleaseError):
        release.profile({"MUSIC_RELEASE_PROFILE": "prod"})  # a typo must not silently mean "development"


def test_commercial_is_not_enabled_by_default_and_exactly_the_three_commercial_presets_are_allowlisted():
    assert release.profile({}) == "development"
    plan = release.manifest()
    assert plan["production_presets"] == ["commercial_2", "commercial_6", "commercial_13"]
    assert all(plan["presets"][name]["problems"] == [] for name in plan["production_presets"])  # owner-approved AND every model gate passes


# --- development keeps working ------------------------------------------------------------------------

def test_development_allows_every_existing_preset(served, monkeypatch):
    request, library, store = served
    monkeypatch.setenv("MUSIC_RELEASE_PROFILE", "development")
    monkeypatch.setattr(library.executor, "submit", lambda *args: None)
    for preset in ("final_11", "basic_6", "basic_2", "commercial_13"):
        release.require_allowed(preset)
        assert request(upload(preset), "POST", b"audio", "alice", {"X-Filename": "a.wav"})[0] == 202
    assert json.loads(request("/api/release")[1]) == {"profile": "development", "presets": None}


# --- commercial: allowlist + fail closed --------------------------------------------------------------

@pytest.mark.parametrize("preset", DEV_PRESETS)
def test_commercial_rejects_development_presets_even_when_called_directly(commercial, monkeypatch, preset):
    submitted = []
    monkeypatch.setattr(commercial.library.executor, "submit", lambda *args: submitted.append(args))
    before = set(commercial.store.owners)
    status, body, _ = commercial.request(upload(preset), "POST", b"audio", "alice", {"X-Filename": "a.wav"})
    assert status == 400 and json.loads(body)["error"] == release.PUBLIC_REFUSAL  # no internal detail leaks
    assert submitted == [] and set(commercial.store.owners) == before
    assert not list(commercial.library.web.glob("analysis_*/source.*"))
    with pytest.raises(release.ReleaseError):
        release.require_allowed(preset, commercial.library.root)


def test_commercial_default_preset_is_not_a_fallback(commercial, monkeypatch):
    monkeypatch.setattr(commercial.library.executor, "submit", lambda *args: None)
    status, _, _ = commercial.request("/api/analyses?rights=" + RIGHTS_CONFIRMATION_VERSION, "POST", b"a", "alice", {"X-Filename": "a.wav"})
    assert status == 400  # the handler's legacy default (final_10) is a development preset


def test_commercial_allows_an_approved_preset(commercial, monkeypatch):
    monkeypatch.setattr(commercial.library.executor, "submit", lambda *args: None)
    release.require_allowed("commercial_13", commercial.library.root)
    status, body, _ = commercial.request(upload("commercial_13"), "POST", b"audio", "alice", {"X-Filename": "a.wav"})
    assert status == 202
    assert json.loads(commercial.request("/api/release")[1]) == {"profile": "commercial", "presets": ["commercial_13"]}


def test_commercial_blocks_vocal_detail_which_uses_development_models(commercial):
    identifier, *_ = stored_analysis(commercial.library, commercial.store, "alice", "1")
    status, body, _ = commercial.request(f"/api/analyses/{identifier}/vocal-detail", "POST", b"{}", "alice")
    assert status == 400 and json.loads(body)["error"] == release.PUBLIC_REFUSAL


def test_commercial_jobs_must_belong_to_an_approved_preset(commercial):
    for stage in release.stage_presets_for("commercial_13"):
        release.require_stage(stage)
    for stage in ("instrument_roformer_6s", "bs_karaoke", "htdemucs", "clapsep"):
        with pytest.raises(release.ReleaseError):
            release.require_stage(stage)


def test_unknown_model_dependency_fails_closed(commercial, monkeypatch):
    commercial.approve(**{commercial.models[-1]: {"status": "UNKNOWN"}})
    with pytest.raises(release.ReleaseError) as error:
        release.require_allowed("commercial_13", commercial.library.root)
    assert str(error.value) == release.PUBLIC_REFUSAL and "UNKNOWN" in error.value.detail
    with pytest.raises(release.ReleaseError):
        release.validate_production()
    assert commercial.request(upload("commercial_13"), "POST", b"a", "alice", {"X-Filename": "a.wav"})[0] == 400


def test_blocked_weight_license_fails_closed(commercial, monkeypatch):
    real = registry.config
    def config(model_id="demucs_htdemucs"):
        entry = real(model_id)
        return {**entry, "weight_license": {"value": "UNKNOWN", "status": "UNVERIFIED"}} if model_id == commercial.models[0] else entry
    monkeypatch.setattr(registry, "config", config)
    with pytest.raises(release.ReleaseError) as error:
        release.validate_preset("commercial_13", commercial.library.root)
    assert "weight license" in error.value.detail


def test_approval_hash_that_differs_from_the_registry_fails_closed(commercial):
    commercial.approve(**{commercial.models[0]: {"checkpoint_sha256": "0" * 64}})
    with pytest.raises(release.ReleaseError) as error:
        release.require_allowed("commercial_13", commercial.library.root)
    assert "differs from the registry sha256" in error.value.detail


def test_checkpoint_registration_hash_mismatch_fails_closed(commercial):
    write_json(commercial.library.root / "models" / commercial.models[0] / "registration.json", {"checkpoint_sha256": "f" * 64})
    with pytest.raises(release.ReleaseError) as error:
        release.require_allowed("commercial_13", commercial.library.root)
    assert "approved hash" in error.value.detail


def test_missing_registration_fails_closed(commercial):
    (commercial.library.root / "models" / commercial.models[0] / "registration.json").unlink()
    with pytest.raises(release.ReleaseError):
        release.require_allowed("commercial_13", commercial.library.root)


def test_missing_or_broken_allowlist_config_fails_closed(commercial, monkeypatch):
    monkeypatch.setattr(release, "CONFIG", commercial.tmp / "does-not-exist.json")
    with pytest.raises(release.ReleaseError) as error:
        release.require_allowed("commercial_13", commercial.library.root)
    assert "RELEASE_CONFIG_MISSING" in error.value.detail
    broken = commercial.tmp / "broken.json"
    broken.write_text("{not json")
    monkeypatch.setattr(release, "CONFIG", broken)
    with pytest.raises(release.ReleaseError):
        release.startup_check(commercial.library.root)


def test_allowlisted_preset_without_a_stage_mapping_fails_closed(commercial):
    config = read_json(commercial.config)
    config["commercial"]["presets"]["commercial_99"] = {"status": "APPROVED"}
    write_json(commercial.config, config)
    with pytest.raises(release.ReleaseError) as error:
        release.require_allowed("commercial_13", commercial.library.root)
    assert "RELEASE_PRESET_UNMAPPED" in error.value.detail


def test_stage_mapping_that_names_a_missing_preset_fails_closed(commercial, monkeypatch):
    monkeypatch.setitem(release.STAGE_RESOLVERS, "commercial_13", lambda: ["no_such_stage_preset"])
    with pytest.raises(release.ReleaseError) as error:
        release.require_allowed("commercial_13", commercial.library.root)
    assert "RELEASE_PRESET_MISMATCH" in error.value.detail


def test_invalid_profile_value_refuses_requests(served, monkeypatch):
    request, library, store = served
    monkeypatch.setenv("MUSIC_RELEASE_PROFILE", "comercial")
    monkeypatch.setattr(library.executor, "submit", lambda *args: None)
    assert request(upload("basic_2"), "POST", b"a", "alice", {"X-Filename": "a.wav"})[0] == 400
    assert json.loads(request("/api/release")[1]) == {"profile": "commercial", "presets": []}


def test_commercial_server_refuses_to_start_with_a_failing_preset(commercial):
    assert release.startup_check(commercial.library.root) == "commercial"
    commercial.approve(**{commercial.models[0]: {"status": "BLOCKED"}})
    with pytest.raises(release.ReleaseError):
        release.startup_check(commercial.library.root)


# --- commercial_13 must not reach CLAPSep / LAION-CLAP ------------------------------------------------

def run_for_library_call_sites():
    tree = ast.parse((SRC / "web_server.py").read_text(encoding="utf-8"))
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    sites = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", "")) == "run_for_library":
            chain, current = [], node
            while current in parents:
                child, current = current, parents[current]
                if isinstance(current, ast.If):
                    chain.append((ast.unparse(current.test), child in current.orelse))
            sites.append(chain)
    return sites


def test_clapsep_recovery_is_only_reachable_outside_commercial_13():
    sites = run_for_library_call_sites()
    assert sites, "expected the development call sites to exist"
    for chain in sites:
        excluded = any(("commercial" in test and in_else) or "final_10" in test for test, in_else in chain)
        assert excluded, f"run_for_library (CLAPSep) reachable by commercial_13 under {chain}"


def test_commercial_13_stage_and_model_lists_exclude_clap_models():
    stages = release.stage_presets_for("commercial_13")
    models = release.model_ids_for("commercial_13")
    assert not {"clapsep", "laion_clap", "audiosep_base"} & set(models)
    assert not any("clap" in s.lower() for s in stages)


def test_commercial_modules_never_import_clap_paths():
    for name in ("commercial_pipeline.py", "commercial_cymbal.py"):
        tree = ast.parse((SRC / name).read_text(encoding="utf-8"))
        imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        imported |= {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        assert not {i for i in imported if any(bad in i for bad in ("synth_recovery", "part_study", "clapsep", "laion"))}, name


def test_commercial_cymbal_step_fails_if_clapsep_is_called(tmp_path, monkeypatch):
    """Run the real commercial cymbal stage with every CLAPSep entry point booby-trapped."""
    from music_analyzer import commercial_cymbal, synth_recovery
    def forbidden(*args, **kwargs):
        raise AssertionError("CLAPSep/LAION-CLAP path was called from commercial_13")
    monkeypatch.setattr(synth_recovery, "run_for_library", forbidden)
    monkeypatch.setattr(synth_recovery, "infer", forbidden)
    monkeypatch.setitem(sys.modules, "music_analyzer.part_study", None)  # importing it now raises ImportError
    monkeypatch.setitem(sys.modules, "music_analyzer.clapsep_experiment", None)
    rng = np.random.default_rng(0)
    folder = tmp_path / "web" / ("analysis_" + "a" * 32)
    folder.mkdir(parents=True)
    tracks = []
    for family in ("piano", "drums"):
        path = folder / f"{family}.wav"
        sf.write(path, rng.normal(0, .05, (44100, 2)).astype("float32"), 44100, subtype="FLOAT")
        tracks.append({"family": family, "path": str(path.relative_to(tmp_path))})
    row = {"id": folder.name, "tracks": tracks}
    result = commercial_cymbal.apply(tmp_path, row)
    assert result["cymbal_recovery"]["evidence"] == "core4_drums_stem"


# --- production dependencies <-> /licenses -------------------------------------------------------------

def test_committed_notices_match_the_production_plan():
    if not license_notices.NODE.exists():
        pytest.skip("frontend/node_modules not installed")
    assert license_notices.check() == []


def test_manifest_discovers_real_runtime_dependencies():
    runtime = release.manifest()["runtime"]
    assert {"torch", "demucs", "librosa", "numpy", "soundfile", "pymysql"} <= set(runtime["direct"])
    assert "PoPE_pytorch" in runtime["optional_not_installed"]  # guarded optional import is not a dependency
    assert "torchaudio" in runtime["transitive"]


def test_production_manifest_records_models_hashes_and_blockers(commercial):
    plan = release.manifest()
    entry = plan["presets"]["commercial_13"]
    assert plan["production_presets"] == ["commercial_13"] and entry["problems"] == []
    assert {m["model_id"] for m in entry["models"]} == set(commercial.models)
    assert all(m["approved_sha256"] and m["registry_sha256_prefix"] and m["weight_license"] for m in entry["models"])


@pytest.fixture
def built(commercial, monkeypatch):
    if not license_notices.NODE.exists():
        pytest.skip("frontend/node_modules not installed")
    out = commercial.tmp / "licenses"
    license_notices.build(out)
    return commercial, out


def test_notices_built_from_an_approved_preset_list_exactly_its_models(built):
    commercial, out = built
    shown = json.loads((out / "models.json").read_text(encoding="utf-8"))
    assert {m["name"] for m in shown} == {"Mel-Band RoFormer 가중치", "MVSep Mega53 계열 가중치"}
    assert license_notices.check(out) == []
    dumped = json.dumps([{k: v for k, v in m.items() if k != "evidence"} for m in shown], ensure_ascii=False)  # evidence is a link
    for model in commercial.models:
        assert model not in dumped and registry.config(model)["upstream_sha256_prefix"] not in dumped


def test_notice_check_flags_a_model_production_does_not_use(built):
    _, out = built
    shown = json.loads((out / "models.json").read_text(encoding="utf-8"))
    write_json(out / "models.json", shown + [{"name": "CLAPSep 가중치", "author": "x", "license": "MIT (저작자 선언)", "url": "https://x", "evidence": "https://x"}])
    assert any("shows a model production does not use" in p for p in license_notices.check(out))


def test_notice_check_flags_a_production_model_missing_from_licenses(built):
    _, out = built
    shown = json.loads((out / "models.json").read_text(encoding="utf-8"))
    write_json(out / "models.json", shown[:1])
    assert any("production model missing from /licenses" in p for p in license_notices.check(out))


def test_notice_check_flags_missing_license_text(built):
    _, out = built
    (out / "texts" / "pytorch.txt").unlink()
    assert any("license text missing or stale: pytorch" in p for p in license_notices.check(out))


def test_build_fails_when_a_production_model_has_no_notice_entry(commercial, monkeypatch):
    groups = read_json(license_notices.MODEL_NOTICES)
    groups["models"].pop(commercial.models[0])
    notices, problems = license_notices.compute(group_config=groups)
    assert any("missing license notice" in p and commercial.models[0] in p for p in problems)


def test_build_fails_when_a_runtime_package_has_no_notice(commercial, monkeypatch):
    monkeypatch.setattr(license_notices, "PYTHON", {k: v for k, v in license_notices.PYTHON.items() if k != "librosa"})
    _, problems = license_notices.compute()
    assert any("missing license notice: runtime package librosa" in p for p in problems)


def test_build_fails_when_a_notice_describes_an_unused_package(commercial, monkeypatch):
    monkeypatch.setitem(license_notices.PYTHON, "tensorflow", ("tf", "TensorFlow", "Apache-2.0", "https://x", None))
    _, problems = license_notices.compute()
    assert any("tensorflow" in p and "does not import" in p for p in problems)


def test_build_refuses_a_production_preset_with_an_unknown_model(commercial):
    commercial.approve(**{commercial.models[0]: {"status": "UNKNOWN"}})
    with pytest.raises(release.ReleaseError):
        license_notices.build(commercial.tmp / "out")
    assert not (commercial.tmp / "out").exists()


def test_ui_versions_map_to_runtime_presets_in_the_allowlist():
    """The UI keeps its own ids and sends `commercial:` ids under the commercial profile; they must match the server allowlist."""
    text = (Path(release.__file__).parents[3] / "frontend/src/versions.js").read_text(encoding="utf-8")
    ui_presets = set(__import__("re").findall(r"commercial:'(commercial_\d+)'", text))
    assert "commercial_13" in ui_presets and ui_presets >= set(release.STAGE_RESOLVERS)
    assert set(release.STAGE_RESOLVERS) <= set(read_json(release.CONFIG)["commercial"]["presets"])
