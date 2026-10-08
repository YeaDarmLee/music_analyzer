"""Output / storage lifecycle: keep only what the user needs once an analysis is over.

MUSIC_KEEP_INTERMEDIATES (default off) keeps every model output, evidence stem, routing scratch and intermediate asset for development and
benchmarks. MUSIC_CACHE_TTL_HOURS (default 24) bounds the lazily rebuilt playback caches. Both come from the same place as MUSIC_RELEASE_PROFILE
(.env + environment, see auth.load_settings).

Rules
- Only files that belong to ONE finished analysis are removed: its web/<id> folder, the job result folders and intermediate assets of its own
  job_ids. A job or asset that any other analysis record or pipeline manifest still names is never touched (same rule as WebLibrary.delete).
- Success promotes the deliverables into the analysis folder first: web/<id>/final/<family>.wav, web/<id>/original.wav and manifest.json
  (the single source of truth for the persistent assets; sha256 and size per file). Everything else of the analysis is then scratch.
- Everything is best effort and idempotent: a failure is reported in the result, never raised, and a second run finds nothing left to do.
- job.json and the attempt logs stay (kilobytes): they let WebLibrary.delete find assets and give a failure trail.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import time
from pathlib import Path

KEEP_ENV = "MUSIC_KEEP_INTERMEDIATES"
KEEP_AUDIO_ENV = "MUSIC_KEEP_BENCHMARK_AUDIO"
TTL_ENV = "MUSIC_CACHE_TTL_HOURS"
TRUE = ("1", "true", "yes", "on")
STORED_ID = re.compile(r"(?:job|asset)_[0-9a-f]{32}")
TERMINAL = ("SUCCEEDED", "FAILED", "CANCELLED")
CACHE_DIRS = ("previews", "enhanced", "bundles")
STALE_PARTIAL_SEC = 3600


def _settings(settings=None):
    if settings is not None:
        return settings
    from .auth import load_settings
    return load_settings()


def keep_intermediates(settings=None) -> bool:
    return str(_settings(settings).get(KEEP_ENV, "")).strip().lower() in TRUE


def cache_ttl_sec(settings=None) -> float:
    try:
        return max(0., float(_settings(settings).get(TTL_ENV, 24))) * 3600
    except (TypeError, ValueError):
        return 24 * 3600


def tree_bytes(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) if path.is_dir() else 0


def tree_files(path: Path) -> int:
    return sum(1 for f in path.rglob("*") if f.is_file()) if path.is_dir() else 0


def ids_in(text: str) -> set[str]:
    return set(STORED_ID.findall(text))


def referenced_elsewhere(root: Path, identifier: str) -> set[str]:
    """job_/asset_ ids named by any other analysis record or pipeline manifest, plus the assets of every job we do not own."""
    kept: set[str] = set()
    for path in (*(root / "web").glob("analysis_*/record.json"), *(root / "pipelines").glob("*/manifest.json")):
        if path.parent.name != identifier:
            try:
                kept |= ids_in(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                pass
    return kept


def live_files(root: Path, record: dict) -> set[Path]:
    """Files the finished analysis serves: every track and the canonical original."""
    live = set()
    for value in [t.get("path") for t in record.get("tracks", [])] + [record.get("original")]:
        if value:
            live.add((root / value).resolve())
    return live


class _Report:
    def __init__(self, dry_run=False):
        self.dry_run = dry_run
        self.freed = 0
        self.files = 0
        self.errors: list[str] = []

    def remove_file(self, path: Path):
        try:
            size = path.stat().st_size
            if not self.dry_run:
                path.unlink()
            self.freed += size
            self.files += 1
        except FileNotFoundError:
            pass
        except OSError as error:
            self.errors.append(f"{path.name}: {error}")

    def remove_tree(self, path: Path):
        try:
            if path.is_symlink():
                path.unlink()
                return
            if not path.exists():
                return
            size, count = tree_bytes(path), tree_files(path)
            if not self.dry_run:
                shutil.rmtree(path)
            self.freed += size
            self.files += count
        except FileNotFoundError:
            pass
        except OSError as error:
            self.errors.append(f"{path.name}: {error}")


def _prune_dir(path: Path, live: set[Path], report: _Report) -> bool:
    """Delete every file under path that is not live, then empty directories. True when something live remains."""
    if not path.is_dir() or path.is_symlink():
        return False
    remains = False
    for child in sorted(path.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if child.is_file():
            if child.resolve() in live:
                remains = True
            else:
                report.remove_file(child)
        elif child.is_dir() and not report.dry_run:
            try:
                child.rmdir()
            except OSError:
                pass
    return remains


def job_asset_id(root: Path, job_id: str) -> set[str]:
    try:
        asset = json.loads((root / "jobs" / job_id / "job.json").read_text(encoding="utf-8")).get("asset_id")
    except (OSError, ValueError):
        return set()
    return {asset} if isinstance(asset, str) else set()


def _sha256(path: Path) -> str:
    import hashlib
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def promote(root: Path, record: dict, elsewhere: set[str]) -> list[str]:
    """Move final tracks and the canonical original under web/<id>/ and write manifest.json. Mutates record paths. Returns errors; on error nothing moved stays moved."""
    folder = root / "web" / record["id"]
    final = folder / "final"
    moved: list[tuple[Path, Path]] = []
    new_paths: dict[int, str] = {}
    try:
        final.mkdir(parents=True, exist_ok=True)
        assets = []
        for index, track in enumerate(record.get("tracks", [])):
            source = (root / track["path"]).resolve()
            target = final / f"{track['family']}{source.suffix}"
            if source != target.resolve():
                os.replace(source, target)
                moved.append((target, source))
            new_paths[index] = str(target.relative_to(root))
            assets.append({"family": track["family"], "path": str(target.relative_to(folder)).replace("\\", "/"),
                           "sha256": track.get("sha256") or _sha256(target), "bytes": target.stat().st_size})
        original = {}
        if record.get("original"):
            source = (root / record["original"]).resolve()
            target = folder / ("original" + source.suffix)
            if source != target.resolve():
                asset_shared = any(a in elsewhere for a in ids_in(str(source)))
                if asset_shared:
                    shutil.copy2(source, target)
                else:
                    os.replace(source, target)
                    moved.append((target, source))
            new_paths[-1] = str(target.relative_to(root))
            original = {"path": target.name, "sha256": _sha256(target), "bytes": target.stat().st_size}
        manifest = {"schema_version": "1.0", "analysis_id": record["id"], "model": record.get("model"),
                    "final_assets": assets, "original": original}
        partial = folder / "manifest.json.partial"
        partial.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        partial.replace(folder / "manifest.json")
    except OSError as error:
        for target, source in reversed(moved):
            try:
                os.replace(target, source)
            except OSError:
                pass
        return [f"promote: {error}"]
    for index, value in new_paths.items():
        if index == -1:
            record["original"] = value
        else:
            record["tracks"][index]["path"] = value
    return []


def finalize(root: Path, record: dict, success: bool, settings=None, dry_run=False, after_promote=None) -> dict:
    """Remove one finished analysis' intermediates. success=False also drops the user-facing files (nothing was delivered).

    dry_run only counts what would go (nothing is moved or deleted; the canonical original is treated as already promoted).
    after_promote(record) -> list[str] runs between the move into final/ and the deletion; any error it returns stops before anything is deleted."""
    root = Path(root).resolve()
    started = time.monotonic()
    if keep_intermediates(settings) and not dry_run:
        return {"mode": "kept", "freed_bytes": 0, "removed_files": 0, "seconds": 0., "errors": []}
    report = _Report(dry_run)
    identifier = record["id"]
    folder = root / "web" / identifier
    elsewhere = referenced_elsewhere(root, identifier)
    promote_errors = promote(root, record, elsewhere) if success and not dry_run else []
    if success and not dry_run and not promote_errors and after_promote is not None:
        promote_errors = after_promote(record)
        if promote_errors:   # promoted but not verified: keep everything else untouched
            return {"mode": "promoted-unverified", "freed_bytes": 0, "removed_files": 0, "seconds": round(time.monotonic() - started, 3), "errors": promote_errors}
    live = live_files(root, record) if success else set()
    if success and not promote_errors and not dry_run:
        live |= {(folder / "manifest.json").resolve(), (folder / "record.json").resolve()}
    report.errors.extend(promote_errors)
    job_ids = [j for j in record.get("job_ids", []) if re.fullmatch(r"job_[0-9a-f]{32}", str(j))]
    for other in (root / "jobs").glob("job_*"):  # assets used by jobs this analysis does not own stay
        if other.name not in job_ids:
            elsewhere |= job_asset_id(root, other.name)
    for job_id in job_ids:  # a job another analysis shares keeps its own asset too
        if job_id in elsewhere:
            elsewhere |= job_asset_id(root, job_id)
    # 1. analysis folder: record.json stays, everything not served goes
    if folder.is_dir():
        for child in folder.iterdir():
            if child.name == "record.json":
                continue
            if child.is_dir():
                _prune_dir(child, live, report)
            elif child.resolve() not in live:
                report.remove_file(child)
    # 2. own jobs: result and scratch go unless a live track lives inside; job.json / attempt logs stay
    assets: set[str] = set()
    for job_id in job_ids:
        assets |= job_asset_id(root, job_id)
        if job_id in elsewhere:
            continue
        job_folder = root / "jobs" / job_id
        for child in ("result",):
            if not _prune_dir(job_folder / child, live, report):
                report.remove_tree(job_folder / child)
        if job_folder.is_dir():
            for partial in job_folder.glob("attempts/*/result.partial"):
                report.remove_tree(partial)
    # 3. own assets: whole directory goes unless a live file is inside it (the upload asset holds the canonical original)
    for asset_id in sorted(assets - elsewhere):
        asset = root / "inputs" / asset_id
        if any(p.is_relative_to(asset.resolve()) for p in live):
            if dry_run:   # the canonical original would have moved out; the rest of the asset goes
                _prune_dir(asset, live, report)
            continue
        report.remove_tree(asset)
    return {"mode": "dry-run" if dry_run else "removed", "freed_bytes": report.freed, "removed_files": report.files,
            "seconds": round(time.monotonic() - started, 3), "errors": report.errors}


def reap(root: Path, active_ids=(), settings=None, now=None) -> dict:
    """Startup / periodic sweep. Never touches the folders of analyses named in active_ids or jobs that are not terminal."""
    root = Path(root).resolve()
    now = time.time() if now is None else now
    report = _Report()
    old = lambda p: now - p.stat().st_mtime > STALE_PARTIAL_SEC
    # interrupted ingests
    for path in (root / "inputs").glob(".partial_*"):
        try:
            if old(path):
                report.remove_tree(path)
        except OSError:
            pass
    # unfinished result folders of finished jobs, partial files of idle analyses
    for job in (root / "jobs").glob("job_*/job.json"):
        try:
            if json.loads(job.read_text(encoding="utf-8")).get("state") in TERMINAL:
                for partial in job.parent.glob("attempts/*/result.partial"):
                    report.remove_tree(partial)
        except (OSError, ValueError):
            pass
    for folder in (root / "web").glob("analysis_*"):
        if folder.name in active_ids:
            continue
        for partial in (*folder.glob("*.partial"), *folder.glob("*.partial.wav")):
            try:
                if old(partial):
                    report.remove_file(partial)
            except OSError:
                pass
    # download archives are per-request temporaries; anything left over is stale (and legacy persistent zips are not kept)
    archives = root / "web" / "archives"
    for path in archives.glob("*.zip") if archives.is_dir() else ():
        try:
            if old(path) or not path.name.startswith("dl-"):
                report.remove_file(path)
        except OSError:
            pass
    for path in archives.glob("*.partial") if archives.is_dir() else ():
        report.remove_file(path)
    # lazily rebuilt playback caches
    ttl = cache_ttl_sec(settings)
    for name in CACHE_DIRS:
        for path in (root / "web" / name).glob("*/*") if (root / "web" / name).is_dir() else ():
            try:
                if now - path.stat().st_mtime > ttl:
                    report.remove_tree(path)
            except OSError:
                pass
    return {"freed_bytes": report.freed, "removed_files": report.files, "errors": report.errors}


def cleanup_unfinalized(root: Path, settings=None) -> list[str]:
    """Records that ended FAILED/CANCELLED (including those marked at server start) and were never finalized: drop their intermediates."""
    root = Path(root).resolve()
    done = []
    for path in (root / "web").glob("analysis_*/record.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if record.get("state") in ("FAILED", "CANCELLED") and "storage" not in record and record.get("kind") != "vocal_detail":
            result = finalize(root, record, False, settings)
            if result["mode"] == "removed":
                record["storage"] = result
                path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
                done.append(record["id"])
    return done


def keep_benchmark_audio(settings=None) -> bool:
    return str(_settings(settings).get(KEEP_AUDIO_ENV, "")).strip().lower() in TRUE


def discard_benchmark_audio(*paths: Path, settings=None) -> dict:
    """Benchmarks keep reports/metrics, not audio: delete the given generated audio folders/files unless MUSIC_KEEP_BENCHMARK_AUDIO=1."""
    if keep_benchmark_audio(settings):
        return {"mode": "kept", "freed_bytes": 0, "removed_files": 0, "errors": []}
    report = _Report()
    for path in paths:
        path = Path(path)
        report.remove_tree(path) if path.is_dir() else report.remove_file(path)
    return {"mode": "removed", "freed_bytes": report.freed, "removed_files": report.files, "errors": report.errors}


def contract_violations(root: Path, identifier: str, max_stray_bytes: int = 64 * 1024) -> list[str]:
    """Files a finished production analysis must not have: anything in web/<id>/ except record.json, manifest.json, original.wav and the
    final/ assets the manifest lists (small stray files up to max_stray_bytes are tolerated), and any audio/array file left in the
    result folders or intermediate assets of its own jobs. Empty list = the contract holds."""
    root = Path(root).resolve()
    folder = root / "web" / identifier
    problems = []
    try:
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        allowed = {"record.json", "manifest.json", manifest["original"]["path"], *(a["path"] for a in manifest["final_assets"])}
    except (OSError, ValueError, KeyError):
        return ["manifest.json missing or unreadable"]
    for path in folder.rglob("*"):
        rel = path.relative_to(folder).as_posix()
        if path.is_file() and rel not in allowed and not rel.startswith(".") and path.stat().st_size > max_stray_bytes:
            problems.append(f"unexpected {rel} ({path.stat().st_size} bytes)")
    for rel in sorted(allowed):
        if not (folder / rel).is_file():
            problems.append(f"missing {rel}")
    try:
        record = json.loads((folder / "record.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return problems + ["record.json unreadable"]
    audio = (".wav", ".flac", ".mp3", ".npz", ".npy")
    for job_id in record.get("job_ids", []):
        for path in (root / "jobs" / str(job_id)).rglob("*") if (root / "jobs" / str(job_id)).is_dir() else ():
            if path.is_file() and path.suffix.lower() in audio:
                problems.append(f"job scratch left: {path.relative_to(root).as_posix()}")
        for asset in job_asset_id(root, str(job_id)):
            if (root / "inputs" / asset).is_dir():
                problems.append(f"intermediate asset left: inputs/{asset}")
    return problems
