"""Isolated, size-capped, fully removable workspace for tests and benchmarks (plan: docs/SIX_TRACK_IMPROVEMENT_PLAN_KO.md section 4).

Everything lives under MUSIC_TEST_ROOT (default <project>/test-workspace, marked by a sentinel file); the service data root is never touched.
Benchmarks get paths only from RunContext. Deletion goes through safe_rmtree, which refuses anything outside <root>/runs (or <root>/reports),
anything containing links or junctions, and any root that is not a marked, non-system directory.
"""
from __future__ import annotations

import json, os, shutil, subprocess, tempfile, time, uuid
from contextlib import contextmanager
from pathlib import Path

import psutil
from filelock import FileLock

from .common import project_root

SENTINEL = ".music-test-root"
GB = 2 ** 30
SCRATCH_DIRS = ("work", "outputs", "cache", "listening")  # removed on normal exit; report/ and inputs/ stay until the run is cleaned
CONFIRM_ALL = "DELETE ALL"
CONFIRM_REPORTS = "DELETE ALL INCLUDING REPORTS"


class TestWorkspaceError(RuntimeError):
    __test__ = False


def _gb(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


def limits() -> dict:
    return {"run_gb": _gb("MUSIC_TEST_RUN_GB", 2), "total_gb": _gb("MUSIC_TEST_TOTAL_GB", 5), "expand_max_gb": _gb("MUSIC_TEST_EXPAND_MAX_GB", 20),
            "min_free_gb": _gb("MUSIC_TEST_MIN_FREE_GB", 20), "retain_days": _gb("MUSIC_TEST_RETAIN_DAYS", 7)}


def root() -> Path:
    return Path(os.environ.get("MUSIC_TEST_ROOT") or project_root() / "test-workspace")


def _is_link(p: Path) -> bool:
    return p.is_symlink() or os.path.isjunction(p)


def contains_link(path: Path) -> bool:
    if _is_link(path):
        return True
    for dirpath, dirs, files in os.walk(path):  # os.walk does not follow links, but reports them as entries
        if any(_is_link(Path(dirpath, n)) for n in dirs + files):
            return True
    return False


def check_root(r: Path | None = None) -> Path:
    """The root must be marked, must not be a drive/home/project root, and must not itself be a link."""
    r = Path(r or root())
    real = Path(os.path.realpath(r))
    forbidden = {Path(real.anchor), Path.home().resolve(), project_root().resolve()}
    if real in forbidden or any(real in f.parents for f in forbidden if f != Path(real.anchor)) or _is_link(r):
        raise TestWorkspaceError(f"refusing test root {real}")
    if not (real / SENTINEL).is_file():
        raise TestWorkspaceError(f"{real} has no {SENTINEL} sentinel")
    return real


def init_root(r: Path | None = None) -> Path:
    r = Path(r or root()); r.mkdir(parents=True, exist_ok=True)
    (r / SENTINEL).touch(exist_ok=True)
    for sub in ("runs", "reports"):
        (r / sub).mkdir(exist_ok=True)
    return check_root(r)


def dir_bytes(p: Path) -> int:
    """Real disk scan (never a counter), so concurrent runs see each other."""
    total = 0
    for dirpath, _, files in os.walk(p):
        for n in files:
            try:
                total += os.lstat(os.path.join(dirpath, n)).st_size
            except OSError:
                pass
    return total


def safe_rmtree(target: Path, r: Path | None = None, allow: tuple[str, ...] = ("runs",)) -> int:
    """Delete target only if it is strictly inside <root>/<allow>. Returns freed bytes. Links are never followed: any link in the tree aborts."""
    real_root = check_root(r)
    t = Path(target)
    if _is_link(t):
        raise TestWorkspaceError(f"refusing {t}: link")
    if not t.exists():
        return 0
    real = Path(os.path.realpath(t))  # a link in any ancestor resolves outside the root and fails the check below
    if not any(real != real_root / a and (real_root / a) in real.parents for a in allow):
        raise TestWorkspaceError(f"refusing {real}: not inside {[str(real_root / a) for a in allow]}")
    if contains_link(real):
        raise TestWorkspaceError(f"refusing {real}: contains a symlink or junction")
    freed = dir_bytes(real) if real.is_dir() else real.stat().st_size
    shutil.rmtree(real) if real.is_dir() else real.unlink()
    return freed


# --- index (run table) ---------------------------------------------------------------------------------------------------------------------

@contextmanager
def _index(r: Path):
    with FileLock(str(r / "index.lock"), timeout=30):
        f = r / "index.json"
        data = json.loads(f.read_text(encoding="utf-8")) if f.is_file() else {"runs": {}}
        yield data
        tmp = r / f"index.{os.getpid()}.tmp"
        tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, f)


def pid_alive(pid: int | None, started: float | None = None) -> bool:
    if not pid or not psutil.pid_exists(pid):
        return False
    try:
        return started is None or abs(psutil.Process(pid).create_time() - started) < 5  # guards against PID reuse
    except psutil.Error:
        return False


def run_status(rec: dict) -> str:
    if rec["status"] == "running" and not pid_alive(rec.get("pid"), rec.get("pid_started")):
        return "orphan"
    return rec["status"]


def estimate_gb(songs: int, seconds: float, stems: int, models: int, sr: int = 44100, ch: int = 2, bytes_per_sample: int = 4) -> float:
    return songs * seconds * sr * ch * bytes_per_sample * stems * models / GB


def new_run(est_gb: float = 0, allow_gb: float | None = None, reason: str = "", r: Path | None = None) -> str:
    """Reserve a run id after checking the estimate against the cap, the total cap and free disk space. allow_gb needs a reason and is recorded."""
    r = init_root(r); lim = limits()
    cap = lim["run_gb"]
    if allow_gb is not None:
        if not reason.strip():
            raise TestWorkspaceError("--allow-gb needs --reason")
        if allow_gb > lim["expand_max_gb"]:
            raise TestWorkspaceError(f"--allow-gb {allow_gb} exceeds the expansion ceiling {lim['expand_max_gb']}")
        cap = max(cap, allow_gb)
    if est_gb > cap:
        raise TestWorkspaceError(f"estimated {est_gb:.2f} GB exceeds the cap {cap:.2f} GB")
    used = dir_bytes(r / "runs") / GB
    if used + est_gb > lim["total_gb"] and allow_gb is None:
        raise TestWorkspaceError(f"estimated total {used + est_gb:.2f} GB exceeds {lim['total_gb']:.2f} GB; clean first")
    if shutil.disk_usage(r).free / GB - est_gb < lim["min_free_gb"]:
        raise TestWorkspaceError(f"free disk space would drop below {lim['min_free_gb']} GB")
    auto_clean_old(r)
    run_id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    (r / "runs" / run_id).mkdir(parents=True)
    now = time.time()
    with _index(r) as idx:
        idx["runs"][run_id] = {"status": "reserved", "started": now, "heartbeat": now, "pid": None, "est_gb": est_gb, "cap_gb": cap,
                               "expansion": {"allow_gb": allow_gb, "reason": reason, "at": now} if allow_gb is not None else None}
    return run_id


class RunContext:
    """with RunContext(est_gb=0.5) as ctx: paths come from ctx.* only; ctx.run() starts child processes with every cache/temp dir redirected."""

    def __init__(self, est_gb: float = 0, allow_gb: float | None = None, reason: str = "", run_id: str | None = None, keep: bool | None = None):
        self.root = init_root()
        self.run_id = run_id or new_run(est_gb, allow_gb, reason, self.root)
        self.dir = self.root / "runs" / self.run_id
        self.keep = bool(os.environ.get("KEEP_TEST_OUTPUT")) if keep is None else keep
        for sub in ("inputs", "report", *SCRATCH_DIRS):
            (self.dir / sub).mkdir(exist_ok=True)
        self.inputs, self.report = self.dir / "inputs", self.dir / "report"
        self.work, self.outputs, self.cache, self.listening = (self.dir / s for s in SCRATCH_DIRS)

    def _update(self, **kw):
        with _index(self.root) as idx:
            idx["runs"][self.run_id].update(kw, heartbeat=time.time())

    def __enter__(self):
        self._update(status="running", pid=os.getpid(), pid_started=psutil.Process().create_time())
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is not None:
            self._update(status="failed", error=f"{exc_type.__name__}: {exc}"[:500], bytes=dir_bytes(self.dir))
            return False
        leftovers = self.leftovers()
        if not self.keep:
            for s in SCRATCH_DIRS:
                safe_rmtree(self.dir / s, self.root); (self.dir / s).mkdir()
        self._update(status="done", ended=time.time(), bytes=dir_bytes(self.dir), leftovers=leftovers)
        return False

    def leftovers(self) -> list[str]:
        """Files in the run directory outside the sanctioned sub-directories."""
        ok = {"inputs", "report", *SCRATCH_DIRS}
        return [p.name for p in self.dir.iterdir() if p.name not in ok]

    def used_bytes(self) -> int:
        return dir_bytes(self.dir)

    def cap_bytes(self) -> float:
        return self.root_rec()["cap_gb"] * GB

    def root_rec(self) -> dict:
        return json.loads((self.root / "index.json").read_text(encoding="utf-8"))["runs"][self.run_id]

    def check_quota(self, extra_bytes: int = 0):
        """Call before writing. Over the cap -> try dropping intermediates, then abort the run."""
        cap = self.cap_bytes()
        if self.used_bytes() + extra_bytes > cap:
            for s in ("work", "cache"):
                safe_rmtree(self.dir / s, self.root); (self.dir / s).mkdir()
            if self.used_bytes() + extra_bytes > cap:
                raise TestWorkspaceError(f"run {self.run_id} would exceed its {cap / GB:.2f} GB cap")
        self._update()

    def env(self) -> dict:
        e = dict(os.environ)
        c = str(self.cache)
        e.update(TMP=c, TEMP=c, TMPDIR=c, XDG_CACHE_HOME=c, NUMBA_CACHE_DIR=c, HF_HOME=c, MPLCONFIGDIR=c, PYTHONPYCACHEPREFIX=c, PYTHONDONTWRITEBYTECODE="1",
                   MUSIC_TEST_ROOT=str(self.root), MUSIC_TEST_RUN_ID=self.run_id)
        e.setdefault("TORCH_HOME", str(Path(os.environ.get("TORCH_HOME", c))))  # weights dir stays wherever the caller already pointed it (read-only use)
        return e

    def run(self, cmd: list[str], **kw) -> subprocess.CompletedProcess:
        self.check_quota()
        return subprocess.run(cmd, cwd=self.work, env=self.env(), **kw)


# --- reporting and cleanup -----------------------------------------------------------------------------------------------------------------

def list_runs(r: Path | None = None) -> list[dict]:
    r = init_root(r)
    with _index(r) as idx:
        rows = [{"run_id": k, **v, "state": run_status(v), "bytes": dir_bytes(r / "runs" / k) if (r / "runs" / k).exists() else 0} for k, v in idx["runs"].items()]
    return rows


def usage(r: Path | None = None) -> dict:
    r = init_root(r); lim = limits(); rows = list_runs(r)
    total = dir_bytes(r / "runs"); reports = dir_bytes(r / "reports")
    return {"root": str(r), "runs_bytes": total, "reports_bytes": reports, "total_cap_gb": lim["total_gb"], "used_ratio": total / (lim["total_gb"] * GB),
            "reclaimable_bytes": total, "runs": [{k: x[k] for k in ("run_id", "state", "bytes")} for x in rows]}


def orphans(r: Path | None = None) -> list[dict]:
    r = init_root(r); known = {x["run_id"] for x in list_runs(r)}
    found = [x for x in list_runs(r) if x["state"] == "orphan"]
    found += [{"run_id": p.name, "state": "unindexed", "bytes": dir_bytes(p)} for p in (r / "runs").iterdir() if p.name not in known]
    return found


def clean_run(run_id: str, dry_run: bool = True, r: Path | None = None) -> int:
    r = init_root(r); d = r / "runs" / run_id
    if Path(run_id).name != run_id or not d.exists():
        raise TestWorkspaceError(f"unknown run {run_id}")
    rec = next((x for x in list_runs(r) if x["run_id"] == run_id), None)
    if rec and rec["state"] in ("running", "reserved") and pid_alive(rec.get("pid"), rec.get("pid_started")):
        raise TestWorkspaceError(f"run {run_id} is still running")
    size = dir_bytes(d)
    if not dry_run:
        safe_rmtree(d, r)
        with _index(r) as idx:
            idx["runs"].pop(run_id, None)
    return size


def clean_all(dry_run: bool = True, confirm: str = "", include_reports: bool = False, r: Path | None = None) -> int:
    r = init_root(r)
    if not dry_run and confirm != (CONFIRM_REPORTS if include_reports else CONFIRM_ALL):
        raise TestWorkspaceError(f"confirmation phrase must be exactly {CONFIRM_REPORTS if include_reports else CONFIRM_ALL!r}")
    freed = 0
    for p in sorted((r / "runs").iterdir()):
        freed += dir_bytes(p)
        if not dry_run:
            safe_rmtree(p, r)
    if include_reports:
        for p in sorted((r / "reports").iterdir()):
            freed += dir_bytes(p) if p.is_dir() else p.stat().st_size
            if not dry_run:
                safe_rmtree(p, r, allow=("reports",))
    if not dry_run:
        with _index(r) as idx:
            idx["runs"].clear()
    return freed


def clean_older_than(days: float, dry_run: bool = True, r: Path | None = None) -> int:
    r = init_root(r); cutoff = time.time() - days * 86400; freed = 0
    for x in list_runs(r):
        if x["state"] in ("done", "failed", "orphan") and x.get("ended", x["started"]) < cutoff:
            freed += clean_run(x["run_id"], dry_run, r)
    return freed


def auto_clean_old(r: Path) -> int:
    return clean_older_than(limits()["retain_days"], dry_run=False, r=r)


# --- one-off cleanup of legacy artefacts (section 4.5) ---------------------------------------------------------------------------------------

PROTECTED = ("data/separation/web", "data/separation/jobs", "data/separation/inputs", "data/separation/models", "data/separation/tools", "song", "docs",
             "separation/tests/fixtures", "separation/src", ".git", ".venv", "frontend/src")
SKIP_WALK = {".git", ".venv", "node_modules", "song"}
PROJECT_GENERATED = ("benchmark-runs", "scratch", "generated", "storage")  # gitignored generated roots


def _protected(p: Path, proj: Path) -> bool:
    real = p.resolve()
    if real != proj and proj not in real.parents:
        return False
    rel = real.relative_to(proj).as_posix()
    return rel == "." or any(rel == q or rel.startswith(q + "/") or q.startswith(rel + "/") for q in PROTECTED)


def legacy_scan(proj: Path | None = None, temp: Path | None = None) -> list[dict]:
    """Read-only. Class 'safe' = regenerable caches; 'confirm' = generated folders a human must approve one by one. Protected paths never appear."""
    proj = Path(proj or project_root()).resolve(); temp = Path(temp or tempfile.gettempdir()); found = []
    def add(p: Path, cls: str, why: str):
        if not _is_link(p) and (cls == "safe" or not _protected(p, proj)):  # caches are regenerable even inside source folders
            found.append({"id": f"L{len(found) + 1}", "path": str(p), "class": cls, "why": why, "bytes": dir_bytes(p) if p.is_dir() else p.stat().st_size,
                          "mtime": p.stat().st_mtime})
    for dirpath, dirs, _ in os.walk(proj):
        dirs[:] = [d for d in dirs if d not in SKIP_WALK and not _is_link(Path(dirpath, d))]
        for d in list(dirs):
            if d in ("__pycache__", ".pytest_cache"):
                add(Path(dirpath, d), "safe", "regenerable cache"); dirs.remove(d)
    for name in PROJECT_GENERATED:
        if (proj / name).exists():
            add(proj / name, "confirm", "generated project folder")
    for p in proj.glob("*.log"):
        add(p, "confirm", "log file")
    for p in temp.glob("pytest-of-*"):
        add(p, "safe", "pytest temp dirs")
    for p in temp.glob("music_analyzer*"):
        add(p, "confirm", "temp folder named after the project")
    return found


def legacy_clean(items: list[dict], approved_ids: set[str], proj: Path | None = None, temp: Path | None = None, dry_run: bool = True) -> int:
    """Safe items go with --yes; 'confirm' items only when listed in approved_ids. Re-checks every path against the protected list and the scan set."""
    proj = Path(proj or project_root()).resolve(); temp = Path(temp or tempfile.gettempdir()); freed = 0
    allowed = {x["path"] for x in legacy_scan(proj, temp)}
    for it in items:
        if it["path"] not in allowed or (it["class"] == "confirm" and it["id"] not in approved_ids):
            continue
        p = Path(it["path"])
        if _is_link(p):
            continue
        if contains_link(p):  # pytest-of-* holds a 'pytest-current' link: drop the links themselves (never their targets), then the tree
            if it["class"] != "safe":
                continue
            if not dry_run:
                for dirpath, dirs, files in os.walk(p):
                    for n in dirs + files:
                        q = Path(dirpath, n)
                        if _is_link(q):
                            os.rmdir(q) if q.is_dir() and not q.is_symlink() else q.unlink()
        if it["class"] == "confirm" and _protected(p, proj):
            continue
        freed += it["bytes"]
        if not dry_run:
            shutil.rmtree(p, ignore_errors=False) if p.is_dir() else p.unlink()
    return freed
