import json
from pathlib import Path
import os
import time

import pytest

from music_analyzer import lifecycle
from music_analyzer.web_server import WebLibrary

A = "analysis_" + "a" * 32
B = "analysis_" + "b" * 32
JOB1, JOB2, JOB3 = ("job_" + c * 32 for c in "123")
UP, MID, MID2 = ("asset_" + c * 32 for c in "567")


def put(root, rel, data=b"x" * 100):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def make_job(root, job_id, asset, files, state="SUCCEEDED"):
    folder = root / "jobs" / job_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "job.json").write_text(json.dumps({"job_id": job_id, "asset_id": asset, "state": state}))
    put(root, f"jobs/{job_id}/attempts/a_1/worker.log", b"log")
    for name in files:
        put(root, f"jobs/{job_id}/result/{name}")


def make_asset(root, asset):
    for name in ("canonical.wav", "original.wav", "manifest.json"):
        put(root, f"inputs/{asset}/{name}")


def make_analysis(root, identifier=A, jobs=(JOB1, JOB2), state="SUCCEEDED", tracks=True):
    put(root, f"web/{identifier}/drums-final.wav")
    put(root, f"web/{identifier}/drums-routed-scratch.wav")
    put(root, f"web/{identifier}/remaining.wav")
    record = {"id": identifier, "state": state, "job_ids": list(jobs), "original": f"inputs/{UP}/canonical.wav",
              "tracks": [{"family": "drums", "path": f"web/{identifier}/drums-final.wav"},
                         {"family": "piano", "path": f"jobs/{JOB1}/result/stems/piano.wav"}] if tracks else []}
    (root / "web" / identifier / "record.json").write_text(json.dumps(record))
    return record


@pytest.fixture
def library_tree(tmp_path, monkeypatch):
    monkeypatch.setenv("MUSIC_KEEP_INTERMEDIATES", "0")
    root = tmp_path
    make_asset(root, UP)
    make_asset(root, MID)
    make_job(root, JOB1, UP, ["manifest.json", "stems/piano.wav", "stems/other.wav"])
    make_job(root, JOB2, MID, ["manifest.json", "stems/vocals.wav", "stems/instrumental.wav"])
    return root, make_analysis(root)


def exists(root, rel):
    return (root / rel).exists()


def test_success_promotes_final_assets_with_manifest_and_removes_the_rest(library_tree):
    root, record = library_tree
    result = lifecycle.finalize(root, record, True)
    assert result["mode"] == "removed" and result["freed_bytes"] > 0 and not result["errors"]
    folder = root / "web" / A
    # canonical layout: record.json, manifest.json, original.wav, final/<family>.wav and nothing else
    assert sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()) == [
        "final/drums.wav", "final/piano.wav", "manifest.json", "original.wav", "record.json"]
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert {a["family"]: a["path"] for a in manifest["final_assets"]} == {"drums": "final/drums.wav", "piano": "final/piano.wav"}
    assert manifest["original"]["path"] == "original.wav" and len(manifest["original"]["sha256"]) == 64
    # the record points at the promoted files (the caller persists it)
    assert Path(record["tracks"][1]["path"]).as_posix() == f"web/{A}/final/piano.wav" and Path(record["original"]).as_posix() == f"web/{A}/original.wav"
    assert (root / record["tracks"][0]["path"]).exists() and (root / record["original"]).exists()
    # all scratch is gone: job results, intermediate assets and the upload asset (its canonical audio moved into the analysis)
    assert not exists(root, f"jobs/{JOB1}/result") and not exists(root, f"jobs/{JOB2}/result")
    assert not exists(root, f"inputs/{MID}") and not exists(root, f"inputs/{UP}")
    # trail stays: job.json and logs
    assert exists(root, f"jobs/{JOB2}/job.json") and exists(root, f"jobs/{JOB2}/attempts/a_1/worker.log")


def test_cleanup_is_idempotent(library_tree):
    root, record = library_tree
    first = lifecycle.finalize(root, record, True)
    second = lifecycle.finalize(root, record, True)
    assert first["freed_bytes"] > 0 and second["freed_bytes"] == 0 and second["removed_files"] == 0 and not second["errors"]


def test_keep_flag_keeps_everything(library_tree, monkeypatch):
    root, record = library_tree
    monkeypatch.setenv("MUSIC_KEEP_INTERMEDIATES", "1")
    assert lifecycle.finalize(root, record, True)["mode"] == "kept"
    assert exists(root, f"web/{A}/remaining.wav") and exists(root, f"inputs/{MID}/canonical.wav")


def test_failure_cleanup_drops_everything_but_the_record_and_job_trail(library_tree):
    root, _ = library_tree
    record = make_analysis(root, A, state="FAILED", tracks=False)
    result = lifecycle.finalize(root, record, False)
    assert result["mode"] == "removed"
    assert exists(root, f"web/{A}/record.json")
    assert not any(p.suffix == ".wav" for p in (root / "web" / A).iterdir())
    assert not exists(root, f"jobs/{JOB1}/result") and not exists(root, f"inputs/{UP}") and not exists(root, f"inputs/{MID}")
    assert exists(root, f"jobs/{JOB1}/job.json") and exists(root, f"jobs/{JOB1}/attempts/a_1/worker.log")


def test_shared_job_and_asset_are_never_removed(library_tree):
    root, record = library_tree
    # another analysis still names JOB2 and the intermediate asset MID2 (through its own job JOB3)
    make_asset(root, MID2)
    make_job(root, JOB3, MID2, ["manifest.json", "stems/vocals.wav"])
    other = make_analysis(root, B, jobs=(JOB2, JOB3))
    other["tracks"][1]["path"] = f"web/{B}/drums-final.wav"
    (root / "web" / B / "record.json").write_text(json.dumps(other))
    lifecycle.finalize(root, record, True)
    assert exists(root, f"jobs/{JOB2}/result/stems/vocals.wav")      # shared job untouched
    assert exists(root, f"inputs/{MID}/canonical.wav")                # asset of the shared job untouched
    assert exists(root, f"jobs/{JOB3}/result/stems/vocals.wav") and exists(root, f"inputs/{MID2}/canonical.wav")
    assert not exists(root, f"jobs/{JOB1}/result")                   # own job still cleaned
    # the other analysis' final stems are not affected
    assert exists(root, f"web/{B}/drums-final.wav") and other["id"] == B


def test_asset_of_a_job_owned_by_someone_else_is_protected(library_tree):
    root, record = library_tree
    make_job(root, JOB3, MID, ["manifest.json"])  # job not in this analysis' job_ids but uses asset MID
    lifecycle.finalize(root, record, True)
    assert exists(root, f"inputs/{MID}/canonical.wav")


def test_active_job_and_active_analysis_survive_reap(tmp_path, monkeypatch):
    root = tmp_path
    now = time.time()
    make_job(root, JOB1, UP, [], state="RUNNING")
    running_partial = put(root, f"jobs/{JOB1}/attempts/a_1/result.partial/stems/x.wav")
    make_job(root, JOB2, UP, [], state="FAILED")
    dead_partial = put(root, f"jobs/{JOB2}/attempts/a_1/result.partial/stems/x.wav")
    make_analysis(root, A, state="RUNNING", jobs=(JOB1,))
    fresh = put(root, f"web/{A}/live.partial.wav")
    lifecycle.reap(root, active_ids={A}, now=now + 10 * 3600)
    assert running_partial.exists()      # job not terminal: left to the supervisor's own recovery
    assert not dead_partial.exists()     # terminal job: partial is garbage
    assert fresh.exists()                # active analysis folder untouched even when old


def test_reap_removes_stale_partials_and_legacy_zips_but_not_fresh_ones(tmp_path):
    root = tmp_path
    stale_ingest = put(root, "inputs/.partial_asset_" + "9" * 32 + "/canonical.wav")
    zip_dir = root / "web" / "archives"
    legacy = put(root, f"web/archives/{A}_deadbeef.zip")
    live_download = put(root, "web/archives/dl-" + "c" * 32 + ".zip")
    make_analysis(root, A)
    partial = put(root, f"web/{A}/x.partial.wav")
    far = time.time() + 2 * 3600
    lifecycle.reap(root, now=far)
    assert not stale_ingest.exists() and not legacy.exists() and not partial.exists()
    assert not live_download.exists()    # even a dl- zip is dropped once it is an hour old
    assert zip_dir.exists()
    fresh = put(root, "web/archives/dl-" + "d" * 32 + ".zip")
    lifecycle.reap(root)
    assert fresh.exists()                # a download that is being served right now survives


def test_cache_ttl_prunes_only_expired_playback_caches(tmp_path):
    old = put(tmp_path, f"web/previews/{A}/fp/piano.wav")
    new = put(tmp_path, f"web/previews/{B}/fp/piano.wav")
    os.utime(old.parent, (1, 1))
    lifecycle.reap(tmp_path, settings={"MUSIC_CACHE_TTL_HOURS": "1"})
    assert not old.parent.exists() and new.exists()


def test_server_restart_marks_running_failed_and_cleans_their_intermediates(library_tree):
    root, _ = library_tree
    make_analysis(root, A, state="RUNNING", tracks=False)
    library = WebLibrary(root)
    try:
        record = json.loads((root / "web" / A / "record.json").read_text(encoding="utf-8"))
        assert record["state"] == "FAILED" and record["storage"]["mode"] == "removed"
        assert not exists(root, f"web/{A}/remaining.wav") and not exists(root, f"jobs/{JOB1}/result")
        assert exists(root, f"jobs/{JOB1}/job.json")
    finally:
        library.executor.shutdown(wait=True)
    before = (root / "web" / A / "record.json").read_text(encoding="utf-8")
    WebLibrary(root).executor.shutdown(wait=True)
    assert (root / "web" / A / "record.json").read_text(encoding="utf-8") == before  # second restart finds nothing to do


def test_download_zip_is_a_unique_temporary_file_and_discard_removes_it(tmp_path):
    import zipfile
    root = tmp_path
    put(root, "web/a.wav", b"RIFFaaaa")
    library = WebLibrary(root)
    try:
        row = {"id": A, "name": "song", "state": "SUCCEEDED", "tracks": [{"family": "drums", "path": "web/a.wav"}], "model": "basic_6",
               "duration": 1}
        first, second = library.archive(row), library.archive(row)
        assert first != second and first.name.startswith("dl-") and first.exists() and second.exists()
        with zipfile.ZipFile(first) as archive:
            assert archive.read("drums.wav") == b"RIFFaaaa"
        library.discard_archive(first)
        assert not first.exists() and second.exists()   # concurrent downloads never delete each other's file
        library.discard_archive(first)                  # idempotent
        assert not list((root / "web" / "archives").glob("*.partial"))
    finally:
        library.executor.shutdown(wait=True)


def test_analysis_delete_still_works_after_cleanup(library_tree):
    root, record = library_tree
    lifecycle.finalize(root, record, True)
    library = WebLibrary(root)
    try:
        library.delete(A)
        assert not exists(root, f"web/{A}") and not exists(root, f"jobs/{JOB1}") and not exists(root, f"inputs/{UP}")
    finally:
        library.executor.shutdown(wait=True)


def test_every_success_path_of_analyze_finalizes_its_outputs():
    import inspect
    from music_analyzer.web_server import WebLibrary as W
    source = inspect.getsource(W.analyze)
    assert source.count('save(state="SUCCEEDED"') == source.count("self.finish_outputs(row,True)")
    assert 'self.finish_outputs(row,False)' in source


def test_contract_holds_after_success_and_flags_a_left_over_intermediate(library_tree):
    root, record = library_tree
    lifecycle.finalize(root, record, True)
    assert lifecycle.contract_violations(root, A) == []
    # a regression that forgets to clean a big scratch file is caught, whatever its name
    put(root, f"web/{A}/some-new-stage-output.wav", b"x" * 200_000)
    put(root, f"jobs/{JOB1}/result/stems/core4-raw.wav")
    found = lifecycle.contract_violations(root, A)
    assert any("some-new-stage-output.wav" in f for f in found) and any("job scratch left" in f for f in found)
    # a missing deliverable is a violation too
    (root / "web" / A / "final" / "drums.wav").unlink()
    assert any("missing final/drums.wav" in f for f in lifecycle.contract_violations(root, A))


def test_dry_run_changes_nothing_and_reports_the_same_savings(library_tree):
    root, record = library_tree
    before = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
    dry = lifecycle.finalize(root, json.loads(json.dumps(record)), True, dry_run=True)
    assert dry["mode"] == "dry-run" and dry["freed_bytes"] > 0
    assert sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()) == before
    real = lifecycle.finalize(root, record, True)
    assert real["freed_bytes"] >= dry["freed_bytes"] - 300   # the real run additionally drops the upload asset's non-canonical files


def test_unverified_promotion_deletes_nothing_else(library_tree):
    root, record = library_tree
    result = lifecycle.finalize(root, record, True, after_promote=lambda r: ["size differs"])
    assert result["mode"] == "promoted-unverified" and result["errors"] == ["size differs"]
    assert exists(root, f"jobs/{JOB1}/result/stems/other.wav") and exists(root, f"inputs/{MID}/canonical.wav")
    assert exists(root, f"web/{A}/final/piano.wav")   # promoted, and the record already points at it
