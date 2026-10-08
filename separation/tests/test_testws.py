import json, os, subprocess, sys, time
from pathlib import Path

import pytest

from music_analyzer import testws as t


@pytest.fixture
def ws(tmp_path, monkeypatch):
    root = tmp_path / "ws"
    monkeypatch.setenv("MUSIC_TEST_ROOT", str(root))
    monkeypatch.setenv("MUSIC_TEST_MIN_FREE_GB", "0")
    monkeypatch.delenv("KEEP_TEST_OUTPUT", raising=False)
    t.init_root()
    return root


def write(p: Path, n: int = 100):
    p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(b"x" * n); return p


def test_clean_run_only_touches_test_runs(ws, tmp_path):
    outside = write(tmp_path / "outside.wav")
    with t.RunContext() as c:
        write(c.work / "a.wav"); rid = c.run_id
    assert t.clean_run(rid, dry_run=False) >= 0
    assert not (ws / "runs" / rid).exists() and outside.exists() and (ws / t.SENTINEL).exists()


def test_rejects_escapes_and_wrong_roots(ws, tmp_path):
    victim = write(tmp_path / "victim" / "keep.txt")
    for bad in (victim.parent, ws, ws / "runs", ws / "runs" / ".." / ".." / "victim"):
        with pytest.raises(t.TestWorkspaceError):
            t.safe_rmtree(bad)
    assert victim.exists()
    with pytest.raises(t.TestWorkspaceError):
        t.clean_run("../victim", dry_run=False)
    for bad_root in (t.project_root(), Path.home(), Path(Path.home().anchor), tmp_path / "unmarked"):
        (bad_root).mkdir(exist_ok=True) if bad_root == tmp_path / "unmarked" else None
        with pytest.raises(t.TestWorkspaceError):
            t.check_root(bad_root)


def test_links_are_not_followed(ws, tmp_path):
    target = write(tmp_path / "precious" / "song.wav")
    with t.RunContext() as c:
        link = c.work / "link"
        try:
            subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target.parent)], check=True, capture_output=True) if os.name == "nt" else link.symlink_to(target.parent)
        except (OSError, subprocess.CalledProcessError):
            pytest.skip("cannot create junction/symlink here")
        rid = c.run_id
        c.keep = True
    with pytest.raises(t.TestWorkspaceError):
        t.clean_run(rid, dry_run=False)
    assert target.exists()
    os.rmdir(ws / "runs" / rid / "work" / "link")  # remove the link itself, not the target
    assert target.exists()


def test_usage_returns_to_zero_but_sentinel_and_reports_stay(ws):
    with t.RunContext() as c:
        write(c.report / "m.json", 10); write(c.work / "w.wav", 5000)
    write(ws / "reports" / "keep.json", 20)
    t.clean_all(dry_run=False, confirm=t.CONFIRM_ALL)
    assert t.usage()["runs_bytes"] == 0 and (ws / "reports" / "keep.json").exists() and (ws / t.SENTINEL).exists()
    with pytest.raises(t.TestWorkspaceError):
        t.clean_all(dry_run=False, confirm=t.CONFIRM_ALL, include_reports=True)  # needs the stronger phrase
    assert (ws / "reports" / "keep.json").exists()
    t.clean_all(dry_run=False, confirm=t.CONFIRM_REPORTS, include_reports=True)
    assert not (ws / "reports" / "keep.json").exists() and (ws / t.SENTINEL).exists()


def test_protected_data_survives_every_cleanup(ws, tmp_path):
    proj = tmp_path / "proj"
    keep = [write(proj / p / "f.bin") for p in ("data/separation/web", "data/separation/models", "song", "docs", "separation/tests/fixtures")]
    write(proj / "scratch" / "old.wav"); write(proj / "separation" / "src" / "__pycache__" / "m.pyc")
    temp = tmp_path / "tmp"; write(temp / "pytest-of-x" / "a.txt")
    items = t.legacy_scan(proj, temp)
    paths = {Path(i["path"]).relative_to(proj).as_posix() if proj in Path(i["path"]).parents else Path(i["path"]).name for i in items}
    assert {"scratch", "separation/src/__pycache__", "pytest-of-x"} <= paths
    assert not any(any(k.parent == Path(i["path"]) or Path(i["path"]) in k.parents for k in keep) for i in items)
    t.legacy_clean(items, set(), proj, temp, dry_run=False)  # confirm-class item not approved -> stays
    assert (proj / "scratch" / "old.wav").exists() and not (temp / "pytest-of-x").exists() and all(k.exists() for k in keep)
    ids = {i["id"] for i in t.legacy_scan(proj, temp) if i["path"].endswith("scratch")}
    t.legacy_clean(t.legacy_scan(proj, temp), ids, proj, temp, dry_run=False)
    assert not (proj / "scratch").exists() and all(k.exists() for k in keep)


def test_dry_run_changes_nothing(ws):
    with t.RunContext() as c:
        c.keep = True; write(c.work / "w.wav"); rid = c.run_id
    before = t.dir_bytes(ws)
    assert t.clean_run(rid, dry_run=True) > 0 and t.clean_all(dry_run=True) > 0 and t.dir_bytes(ws) == before
    with pytest.raises(t.TestWorkspaceError):
        t.clean_all(dry_run=False, confirm="")
    assert (ws / "runs" / rid / "work" / "w.wav").exists()


def test_caps_expansion_and_normal_exit_cleanup(ws, monkeypatch):
    monkeypatch.setenv("MUSIC_TEST_RUN_GB", "0.00001")  # ~10 KB
    with pytest.raises(t.TestWorkspaceError):
        t.new_run(est_gb=1)
    with pytest.raises(t.TestWorkspaceError):
        t.new_run(est_gb=1, allow_gb=2)  # no reason
    with pytest.raises(t.TestWorkspaceError):
        t.new_run(est_gb=1, allow_gb=999, reason="x")  # above ceiling
    with pytest.raises(t.TestWorkspaceError):
        with t.RunContext() as c:
            write(c.outputs / "big.wav", 50_000)
            c.check_quota()
    assert t.list_runs()[0]["state"] == "failed"
    monkeypatch.setenv("MUSIC_TEST_RUN_GB", "0.01")
    with t.RunContext(est_gb=0.0001, allow_gb=1, reason="full-song eval") as c:
        write(c.work / "mid.wav", 5000); write(c.report / "m.json", 10); rid = c.run_id
    rec = next(r for r in t.list_runs() if r["run_id"] == rid)
    assert rec["expansion"]["reason"] == "full-song eval" and rec["state"] == "done" and rec["leftovers"] == []
    assert not list((ws / "runs" / rid / "work").iterdir()) and (ws / "runs" / rid / "report" / "m.json").exists()
    assert t.RunContext(run_id=t.new_run(), keep=False).cap_bytes() == 0.01 * t.GB  # expansion did not leak into the next run


def test_child_process_writes_only_inside_run(ws, tmp_path):
    snap = lambda: {str(p) for d in (Path(os.environ["TEMP"]), Path.cwd()) for p in d.glob("*") if "pytest" not in p.name}
    before = snap()
    code = "import tempfile,pathlib,os;f=tempfile.NamedTemporaryFile(delete=False);f.write(b'x');print(f.name);print(os.getcwd())"
    with t.RunContext() as c:
        out = c.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, check=True).stdout.split("\n")
        assert Path(out[0]).parent == c.cache and Path(out[1]) == c.work
    assert snap() == before


def test_concurrent_index_updates_keep_all_runs(ws):
    code = "from music_analyzer import testws as t\nfor _ in range(5): t.new_run()\n"
    env = {**os.environ, "MUSIC_TEST_ROOT": str(ws), "MUSIC_TEST_MIN_FREE_GB": "0"}
    procs = [subprocess.Popen([sys.executable, "-c", code], env=env) for _ in range(4)]
    assert all(p.wait() == 0 for p in procs)
    assert len(t.list_runs()) == 20 and len(list((ws / "runs").iterdir())) == 20


def test_killed_run_is_orphan_and_cleanable(ws):
    code = "from music_analyzer import testws as t;import time,pathlib\nc=t.RunContext();c.__enter__();(c.work/'w.wav').write_bytes(b'x'*1000);print(c.run_id,flush=True);time.sleep(60)"
    p = subprocess.Popen([sys.executable, "-c", code], env={**os.environ, "MUSIC_TEST_ROOT": str(ws), "MUSIC_TEST_MIN_FREE_GB": "0"}, stdout=subprocess.PIPE, text=True)
    rid = p.stdout.readline().strip()
    assert next(r for r in t.list_runs() if r["run_id"] == rid)["state"] == "running"
    with pytest.raises(t.TestWorkspaceError):
        t.clean_run(rid, dry_run=False)  # alive: refused
    p.kill(); p.wait()
    time.sleep(0.5)
    assert rid in {o["run_id"] for o in t.orphans()}
    t.clean_run(rid, dry_run=False)
    assert not (ws / "runs" / rid).exists() and t.usage()["runs_bytes"] == 0


def test_estimate_gb():
    assert abs(t.estimate_gb(songs=1, seconds=30, stems=6, models=1) - 30 * 44100 * 2 * 4 * 6 / t.GB) < 1e-9
