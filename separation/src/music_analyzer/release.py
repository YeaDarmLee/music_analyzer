"""Release profiles and production preset isolation.

MUSIC_RELEASE_PROFILE = development (default) | commercial

development: every existing preset stays available; nothing in this module is consulted.
commercial:  only presets listed APPROVED in configs/release_presets.json run, and only while every model they
             execute passes validate_preset(). Any problem raises: there is no fallback to a development preset.
"""
from __future__ import annotations

import ast
import functools
import re
import sys
from pathlib import Path

from . import registry
from .common import project_root, read_json

CONFIG = project_root() / "separation/configs/release_presets.json"
PACKAGE = Path(__file__).resolve().parent
PROFILES = ("development", "commercial")
PUBLIC_REFUSAL = "이 분석 구성은 현재 운영 환경에서 제공되지 않습니다."
BLOCKED_LICENSES = ("UNKNOWN", "BLOCKED", "", None)


class ReleaseError(ValueError):
    """`str(error)` is safe to show users; `detail` is for the server log only."""
    def __init__(self, detail, public=PUBLIC_REFUSAL):
        super().__init__(public)
        self.detail = detail


def _stage_presets_commercial_13():
    from .commercial_pipeline import stage_presets
    return stage_presets()


# preset id -> function returning the stage preset names it executes. Extend when commercial_2/6 exist.
STAGE_RESOLVERS = {"commercial_13": _stage_presets_commercial_13}


def profile(settings=None):
    if settings is None:
        from .auth import load_settings
        settings = load_settings()
    value = (str(settings.get("MUSIC_RELEASE_PROFILE", "")).strip().lower()) or "development"
    if value not in PROFILES:
        raise ReleaseError(f"RELEASE_PROFILE_INVALID: {value!r}")
    return value


def config():
    try:
        presets = read_json(CONFIG)["commercial"]["presets"]
        if not isinstance(presets, dict):
            raise TypeError("presets must be an object")
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ReleaseError(f"RELEASE_CONFIG_MISSING: {CONFIG.name}: {error}") from None
    return presets


def stage_presets_for(preset_id):
    resolver = STAGE_RESOLVERS.get(preset_id)
    if resolver is None:
        raise ReleaseError(f"RELEASE_PRESET_UNMAPPED: {preset_id} is allowlisted but has no stage mapping")
    try:
        return list(resolver())
    except ReleaseError:
        raise
    except Exception as error:
        raise ReleaseError(f"RELEASE_PRESET_MAPPING_FAILED: {preset_id}: {error}") from None


def model_ids_for(preset_id):
    from .job_contracts import preset as stage_preset
    try:
        return list(dict.fromkeys(stage_preset(stage)["model_id"] for stage in stage_presets_for(preset_id)))
    except ReleaseError:
        raise
    except Exception as error:
        raise ReleaseError(f"RELEASE_PRESET_MISMATCH: {preset_id}: {error}") from None


def model_record(model_id, approvals):
    """Everything the notice/manifest needs about one model, plus the problems that block production use."""
    approval = approvals.get(model_id, {})
    problems = []
    status = approval.get("status", "UNKNOWN")
    if status != "APPROVED":
        problems.append(f"{model_id}: commercial approval status is {status}")
    try:
        entry = registry.config(model_id)
    except Exception as error:
        return {"model_id": model_id, "approval_status": status, "problems": problems + [f"{model_id}: not in model registry ({error})"]}
    prefix = str(entry.get("upstream_sha256_prefix", "")).lower()
    approved = str(approval.get("checkpoint_sha256", "")).lower()
    if not approved or not prefix or not approved.startswith(prefix):
        problems.append(f"{model_id}: approval sha256 differs from the registry sha256")
    weight = entry.get("weight_license", {})
    if weight.get("value") in BLOCKED_LICENSES:
        problems.append(f"{model_id}: weight license is {weight.get('value')!r}")
    return {"model_id": model_id, "approval_status": status, "approved_sha256": approved or None,
            "registry_sha256_prefix": prefix or None, "weight_license": weight.get("value"),
            "weight_license_status": weight.get("status"), "approval_evidence_url": approval.get("evidence_url"),
            "code_revision": entry.get("code_revision"), "code_license": entry.get("code_license", {}).get("value"),
            "repository_url": entry.get("repository_url"), "problems": problems}


def preset_plan(preset_id, status="APPROVED", approvals=None):
    approvals = read_json(registry.APPROVAL)["models"] if approvals is None else approvals
    models = [model_record(m, approvals) for m in model_ids_for(preset_id)]
    return {"preset": preset_id, "status": status, "stage_presets": stage_presets_for(preset_id), "models": models,
            "problems": [p for m in models for p in m["problems"]]}


def validate_preset(preset_id, data_root=None):
    """Raise unless every model the preset runs is approved, license-known, and hash-consistent."""
    plan = preset_plan(preset_id)
    if plan["problems"]:
        raise ReleaseError("RELEASE_BLOCKED: " + "; ".join(plan["problems"]))
    try:
        registry.commercial_gate([m["model_id"] for m in plan["models"]], data_root)
    except (ValueError, OSError, KeyError) as error:
        raise ReleaseError(f"RELEASE_BLOCKED: {error}") from None
    return plan


def approved_presets():
    """Allowlisted ids that are APPROVED. Every one must be mapped; an unmapped entry is a config error."""
    result = [name for name, entry in config().items() if isinstance(entry, dict) and entry.get("status") == "APPROVED"]
    for name in result:
        stage_presets_for(name)
    return result


def _refuse(error):
    print(f"[release] refused: {error.detail}", file=sys.stderr, flush=True)
    raise ReleaseError(error.detail) from None


def require_allowed(preset_id, data_root=None):
    """Server-side gate for a requested preset. No-op in development; fail closed in commercial."""
    try:
        if profile() == "development":
            return
        if preset_id not in approved_presets():
            raise ReleaseError(f"RELEASE_PRESET_NOT_APPROVED: {preset_id}")
        validate_preset(preset_id, data_root)
    except ReleaseError as error:
        _refuse(error)


def require_stage(stage_preset):
    """Every job a commercial analysis starts must belong to an approved preset."""
    try:
        if profile() == "development":
            return
        if stage_preset not in {s for p in approved_presets() for s in stage_presets_for(p)}:
            raise ReleaseError(f"RELEASE_STAGE_NOT_APPROVED: {stage_preset}")
    except ReleaseError as error:
        _refuse(error)


def require_development(feature):
    try:
        if profile() != "development":
            raise ReleaseError(f"RELEASE_FEATURE_DEV_ONLY: {feature}")
    except ReleaseError as error:
        _refuse(error)


def startup_check(data_root=None):
    """Refuse to start a commercial server whose allowlist or approved presets do not validate."""
    current = profile()
    if current == "commercial":
        for name in approved_presets():
            validate_preset(name, data_root)
    return current


def public_status():
    """What the UI may offer: None means every preset (development)."""
    try:
        if profile() == "development":
            return {"profile": "development", "presets": None}
        return {"profile": "commercial", "presets": approved_presets()}
    except ReleaseError:
        return {"profile": "commercial", "presets": []}


# --- runtime dependency discovery -----------------------------------------------------------------------

def _guards_import(node):
    """True for `try: import x ... except ImportError` and for `except Exception` around a body that only imports."""
    simple = all(isinstance(n, (ast.Import, ast.ImportFrom)) or (isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant))
                 for n in node.body)
    for handler in node.handlers:
        nodes = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
        names = {n.id for n in nodes if isinstance(n, ast.Name)}
        if names & {"ImportError", "ModuleNotFoundError"} or (simple and "Exception" in names):
            return True
    return False


def _visit(node, optional, found):
    if isinstance(node, ast.Import):
        found += [(alias.name.split(".")[0], optional) for alias in node.names]
    elif isinstance(node, ast.ImportFrom):
        if node.level == 0 and node.module:
            found.append((node.module.split(".")[0], optional))
    elif isinstance(node, ast.Try):
        guarded = _guards_import(node)
        for child in node.body:
            _visit(child, optional or guarded, found)
        for child in (*node.handlers, *node.orelse, *node.finalbody):
            _visit(child, optional, found)
    else:
        for child in ast.iter_child_nodes(node):
            _visit(child, optional, found)


def scan_imports(paths):
    """Third-party top-level imports of the given source files: (required, optional)."""
    found = []
    for path in paths:
        _visit(ast.parse(Path(path).read_text(encoding="utf-8")), False, found)
    third = lambda names: {n for n in names if n not in sys.stdlib_module_names and n != "music_analyzer"}
    required = third(n for n, optional in found if not optional)
    return required, third(n for n, optional in found if optional) - required


def normalize(name):
    return re.sub(r"[-_.]+", "-", name).lower()


@functools.lru_cache(maxsize=1)
def _owners():
    import importlib.metadata as metadata
    return metadata.packages_distributions()


def runtime_dependencies(modules=None, extra=None):
    """Python distributions the commercial runtime imports (direct) and their metadata-declared closure (transitive)."""
    import importlib.metadata as metadata
    from packaging.requirements import Requirement
    settings = read_json(CONFIG)["commercial"]
    modules = settings["runtime_modules"] if modules is None else modules
    extra = settings.get("extra_distributions", {}) if extra is None else extra
    required, optional = scan_imports([PACKAGE / m for m in modules])
    owners = _owners()
    direct, unmapped = {}, []
    for name in sorted(required):
        if name not in owners:
            unmapped.append(name)
        for dist in owners.get(name, []):
            direct[normalize(dist)] = metadata.version(dist)
    if unmapped:
        raise ReleaseError("RELEASE_RUNTIME_IMPORT_UNMAPPED: no installed distribution provides " + ", ".join(unmapped))
    for dist in extra:
        direct[normalize(dist)] = metadata.version(dist)
    transitive, queue = {}, list(direct)
    while queue:
        for requirement in metadata.requires(queue.pop()) or []:
            parsed = Requirement(requirement)
            name = normalize(parsed.name)
            if (parsed.marker and not parsed.marker.evaluate({"extra": ""})) or name in direct or name in transitive:
                continue
            try:
                transitive[name] = metadata.version(parsed.name)
            except metadata.PackageNotFoundError:
                continue
            queue.append(name)
    return {"direct": direct, "transitive": dict(sorted(transitive.items())), "optional_not_installed": sorted(optional - set(owners)),
            "external_tools": settings.get("external_tools", [])}


def manifest(approvals=None):
    """Internal production dependency manifest: every configured preset, its models/hashes, and the runtime packages."""
    approvals = read_json(registry.APPROVAL)["models"] if approvals is None else approvals
    presets = {}
    for name, entry in config().items():
        try:
            presets[name] = preset_plan(name, entry.get("status", "UNKNOWN"), approvals)
        except ReleaseError as error:
            presets[name] = {"preset": name, "status": entry.get("status", "UNKNOWN"), "stage_presets": [], "models": [], "problems": [error.detail]}
    return {"schema_version": "1.0", "profile_env": "MUSIC_RELEASE_PROFILE", "presets": presets,
            "production_presets": [n for n, p in presets.items() if p["status"] == "APPROVED"],
            "runtime": runtime_dependencies()}


def validate_production(approvals=None):
    """Raise if any APPROVED preset has blockers or an unmapped stage list (used by the notice build and tests)."""
    result = manifest(approvals)
    problems = [f"{n}: {p}" for n in result["production_presets"] for p in result["presets"][n]["problems"]]
    if problems:
        raise ReleaseError("RELEASE_PRODUCTION_BLOCKED: " + "; ".join(problems))
    return result
