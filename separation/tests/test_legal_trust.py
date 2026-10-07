"""Legal/trust behaviour: signup consent, upload rights confirmation, analysis deletion, withdrawal."""
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from music_analyzer.auth import AuthStore
from music_analyzer.common import write_json
from music_analyzer.legal import PRIVACY_VERSION, RIGHTS_CONFIRMATION_VERSION, TERMS_VERSION
from music_analyzer.web_server import WebLibrary, make_handler

UPLOAD = "/api/analyses?preset=basic_2&rights=" + RIGHTS_CONFIRMATION_VERSION


class MemoryStore(AuthStore):
    """AuthStore with the SQL layer replaced by dicts, so register/consent logic runs for real."""
    def __init__(self):
        super().__init__({})
        self.users, self.consent_rows, self.sessions, self.owners = {}, [], {}, {}

    def throttle(self, address):
        pass

    def transaction(self, statements):
        for sql, args in statements:
            if sql.startswith("INSERT INTO users"):
                self.users[args[0]] = args
            elif sql.startswith("INSERT INTO user_consents"):
                self.consent_rows.append(args)

    def new_session(self, user_id):
        token = "tok-" + user_id
        self.sessions[token] = {"id": user_id}
        return token

    def session_user(self, token):
        return self.sessions.get(token)

    def logout(self, token):
        self.sessions.pop(token, None)

    def owns(self, user_id, identifier):
        return self.owners.get(identifier) == user_id

    def owned_ids(self, user_id):
        return {key for key, owner in self.owners.items() if owner == user_id}

    def assign(self, user_id, identifier):
        self.owners[identifier] = user_id

    def has_current_consents(self, user_id):
        return {(row[1], row[2]) for row in self.consent_rows if row[0] == user_id} == {("TERMS", TERMS_VERSION), ("PRIVACY", PRIVACY_VERSION)}

    def record_consents(self, user_id, consents):
        self.transaction(self.consent_statements(user_id, consents))

    def release(self, identifier):
        self.owners.pop(identifier, None)

    def delete_account(self, user_id):
        self.sessions = {t: u for t, u in self.sessions.items() if u["id"] != user_id}
        self.owners = {k: v for k, v in self.owners.items() if v != user_id}


@pytest.fixture
def served(tmp_path):
    library = WebLibrary(tmp_path)
    store = MemoryStore()
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("studio")
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(library, dist, 0, auth=store))
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()

    def request(path, method="GET", body=None, token=None, headers=None):
        actual = {"X-Requested-With": "MusicAnalyzer", "Content-Type": "application/json", **(headers or {})}
        if token:
            actual["Cookie"] = "music_session=" + token
        data = json.dumps(body).encode() if isinstance(body, dict) else body
        req = urllib.request.Request(f"http://127.0.0.1:{server.server_port}" + path, data=data, method=method, headers=actual)
        try:
            response = urllib.request.urlopen(req)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, response.read(), response.headers

    store.sessions.update(alice={"id": "alice"}, bob={"id": "bob"}, carol={"id": "carol"})
    for member in ("alice", "bob"):  # carol is a legacy member with no consent record
        store.consent_rows += [(member, "TERMS", TERMS_VERSION), (member, "PRIVACY", PRIVACY_VERSION)]
    yield request, library, store
    server.shutdown()
    server.server_close()
    worker.join()
    library.executor.shutdown()


def signup(extra=None):
    return {"email": "a@example.com", "password": "long-enough-password", "display_name": "닉", **(extra or {})}


def test_signup_without_required_consent_creates_no_account(served):
    request, _, store = served
    before, rows = dict(store.sessions), list(store.consent_rows)
    for consents in (None, {}, {"TERMS": TERMS_VERSION}, {"PRIVACY": PRIVACY_VERSION},
                     {"TERMS": "old", "PRIVACY": PRIVACY_VERSION}, {"TERMS": True, "PRIVACY": True}):
        status, body, _ = request("/api/auth/register", "POST", signup({} if consents is None else {"consents": consents}))
        assert status == 400 and "동의" in json.loads(body)["error"]
    assert store.users == {} and store.consent_rows == rows and store.sessions == before


def test_signup_records_terms_and_privacy_versions(served):
    request, _, store = served
    status, body, headers = request("/api/auth/register", "POST",
                                    signup({"consents": {"TERMS": TERMS_VERSION, "PRIVACY": PRIVACY_VERSION}}))
    user = json.loads(body)["user"]
    assert status == 201 and "music_session=" in headers["Set-Cookie"]
    assert {(row[1], row[2]) for row in store.consent_rows if row[0] == user["id"]} == {
        ("TERMS", TERMS_VERSION), ("PRIVACY", PRIVACY_VERSION)}


def test_policy_versions_are_public(served):
    request, _, _ = served
    status, body, _ = request("/api/legal")
    assert status == 200 and json.loads(body) == {
        "terms": TERMS_VERSION, "privacy": PRIVACY_VERSION, "copyright": RIGHTS_CONFIRMATION_VERSION}


@pytest.mark.parametrize("path", ["/terms", "/privacy", "/copyright", "/licenses"])
def test_legal_pages_are_served_without_login(served, path):
    request, _, _ = served
    status, body, _ = request(path)
    assert status == 200 and body == b"studio"


@pytest.mark.parametrize("query", ["", "&rights=", "&rights=old-version"])
def test_analysis_requires_current_rights_confirmation(served, monkeypatch, query):
    request, library, store = served
    calls = []
    monkeypatch.setattr(library.executor, "submit", lambda *args: calls.append(args))
    status, body, _ = request("/api/analyses?preset=basic_2" + query, "POST", b"audio", "alice", {"X-Filename": "my.wav"})
    assert status == 400 and "권한" in json.loads(body)["error"]
    assert calls == [] and store.owners == {} and not list(library.web.glob("analysis_*"))


def test_rights_confirmation_version_and_time_are_recorded(served, monkeypatch):
    request, library, _ = served
    monkeypatch.setattr(library.executor, "submit", lambda *args: None)
    status, body, _ = request(UPLOAD, "POST", b"audio", "alice", {"X-Filename": "my.wav"})
    record = json.loads((library.web / json.loads(body)["id"] / "record.json").read_text(encoding="utf-8"))
    assert status == 202 and record["rights_confirmation_version"] == RIGHTS_CONFIRMATION_VERSION
    assert record["rights_confirmed_at"].endswith("Z")


def stored_analysis(library, store, owner, number, shared_job=None):
    """A finished analysis with its own job, input asset and stage asset on disk."""
    identifier = "analysis_" + number * 32
    job = shared_job or "job_" + number * 32
    asset, stage_asset = "asset_" + number * 32, "asset_" + "f" * 31 + number
    for name in (asset, stage_asset):
        (library.root / "inputs" / name).mkdir(parents=True)
        (library.root / "inputs" / name / "canonical.wav").write_bytes(b"canonical")
    folder = library.root / "jobs" / job
    if not folder.exists():
        (folder / "result" / "stems").mkdir(parents=True)
        (folder / "result" / "stems" / "vocals.wav").write_bytes(b"vocals")
        (folder / "job.json").write_text(json.dumps({"job_id": job, "asset_id": stage_asset}))
    write_json(library.web / identifier / "record.json", {
        "id": identifier, "name": "x", "created": "now", "state": "SUCCEEDED", "duration": 1, "job_ids": [job],
        "tracks": [{"family": "vocals", "path": f"jobs/{job}/result/stems/vocals.wav"}],
        "original": f"inputs/{asset}/canonical.wav"})
    (library.web / identifier / "remaining.wav").write_bytes(b"rest")
    (library.web / "previews" / identifier).mkdir(parents=True)
    store.assign(owner, identifier)
    return identifier, job, asset, stage_asset


def test_member_deletes_own_analysis_and_files_become_inaccessible(served):
    request, library, store = served
    identifier, job, asset, stage_asset = stored_analysis(library, store, "alice", "1")
    assert request("/api/analyses/" + identifier + "/download/vocals", token="alice")[0] == 200
    assert request("/api/analyses/" + identifier, "DELETE", token="alice")[0] == 200
    assert not (library.web / identifier).exists() and not (library.web / "previews" / identifier).exists()
    assert not (library.root / "jobs" / job).exists()
    assert not (library.root / "inputs" / asset).exists() and not (library.root / "inputs" / stage_asset).exists()
    assert not store.owns("alice", identifier)
    for suffix in ("", "/download/vocals", "/audio/original", "/archive"):
        assert request("/api/analyses/" + identifier + suffix, token="alice")[0] == 404
    assert json.loads(request("/api/analyses", token="alice")[1]) == []


def test_member_cannot_delete_another_members_analysis(served):
    request, library, store = served
    identifier, job, _, _ = stored_analysis(library, store, "bob", "2")
    assert request("/api/analyses/" + identifier, "DELETE", token="alice")[0] == 404
    assert request("/api/analyses/" + identifier, "DELETE")[0] == 401
    assert request("/api/analyses/" + identifier, "DELETE", token="bob", headers={"X-Requested-With": ""})[0] == 403
    assert (library.web / identifier / "record.json").exists() and (library.root / "jobs" / job).exists()
    assert store.owns("bob", identifier)


def test_delete_keeps_files_still_referenced_by_another_analysis(served):
    request, library, store = served
    first, job, asset, _ = stored_analysis(library, store, "alice", "3")
    second, _, second_asset, _ = stored_analysis(library, store, "bob", "4", shared_job=job)
    assert request("/api/analyses/" + first, "DELETE", token="alice")[0] == 200
    assert (library.root / "jobs" / job / "result" / "stems" / "vocals.wav").exists()
    assert (library.root / "inputs" / second_asset).exists() and not (library.root / "inputs" / asset).exists()
    assert request("/api/analyses/" + second + "/download/vocals", token="bob")[0] == 200
    assert request("/api/analyses/" + second, "DELETE", token="bob")[0] == 200
    assert not (library.root / "jobs" / job).exists()


def test_running_analysis_cannot_be_deleted(served):
    request, library, store = served
    identifier, job, _, _ = stored_analysis(library, store, "alice", "5")
    path = library.web / identifier / "record.json"
    write_json(path, {**json.loads(path.read_text(encoding="utf-8")), "state": "RUNNING"})
    status, body, _ = request("/api/analyses/" + identifier, "DELETE", token="alice")
    assert status == 400 and "진행 중" in json.loads(body)["error"]
    assert path.exists() and (library.root / "jobs" / job).exists() and store.owns("alice", identifier)


def test_withdrawal_invalidates_session_and_removes_only_the_members_analyses(served):
    request, library, store = served
    mine, job, _, _ = stored_analysis(library, store, "alice", "6")
    theirs, _, _, _ = stored_analysis(library, store, "bob", "7")
    status, _, headers = request("/api/auth/account", "DELETE", token="alice")
    assert status == 200 and "Max-Age=0" in headers["Set-Cookie"]
    assert "alice" not in store.sessions and not store.owned_ids("alice")
    assert request("/api/analyses", token="alice")[0] == 401
    assert request("/api/analyses/" + mine, token="alice")[0] == 401
    assert not (library.web / mine).exists() and not (library.root / "jobs" / job).exists()
    assert request("/api/analyses/" + theirs + "/download/vocals", token="bob")[0] == 200


def test_withdrawal_is_refused_while_an_analysis_runs(served):
    request, library, store = served
    identifier, _, _, _ = stored_analysis(library, store, "alice", "8")
    path = library.web / identifier / "record.json"
    write_json(path, {**json.loads(path.read_text(encoding="utf-8")), "state": "QUEUED"})
    assert request("/api/auth/account", "DELETE", token="alice")[0] == 400
    assert "alice" in store.sessions and store.owns("alice", identifier) and path.exists()


def test_upload_copy_is_removed_when_preparation_fails_or_finishes(tmp_path, monkeypatch):
    from music_analyzer import web_server
    library = WebLibrary(tmp_path)
    folder = library.web / ("analysis_" + "a" * 32)
    folder.mkdir()
    upload = folder / "source.wav"
    upload.write_bytes(b"raw upload")
    row = {"id": folder.name, "model": "basic_2", "state": "QUEUED", "progress": 0, "tracks": [], "job_ids": []}
    seen = []

    def fake_ingest(path, root):
        seen.append(path.exists())
        raise ValueError("stop right after ingest")
    monkeypatch.setattr(web_server, "ingest_file", fake_ingest)
    library.analyze(folder, upload, row)
    assert seen == [True] and row["state"] == "FAILED" and not upload.exists()
    library.executor.shutdown()


def test_member_without_current_consent_is_gated_until_accepting(served):
    request, library, store = served
    status, body, _ = request("/api/auth/me", token="carol")
    assert status == 200 and json.loads(body)["user"]["consent_required"] is True
    for call in (("/api/analyses",), (UPLOAD, "POST", b"audio", "carol", {"X-Filename": "my.wav"})):
        args = call if len(call) > 1 else (call[0], "GET", None, "carol")
        status, body, _ = request(*args)
        assert status == 403 and "동의" in json.loads(body)["error"]
    assert request("/api/auth/consent", "POST", {"consents": {"TERMS": TERMS_VERSION}}, "carol")[0] == 400
    assert request("/api/auth/consent", "POST", {"consents": {"TERMS": TERMS_VERSION, "PRIVACY": PRIVACY_VERSION}}, "carol")[0] == 200
    assert json.loads(request("/api/auth/me", token="carol")[1])["user"]["consent_required"] is False
    assert request("/api/analyses", token="carol")[0] == 200


def test_outdated_consent_version_gates_again(served, monkeypatch):
    request, _, store = served
    store.consent_rows[:] = [("alice", "TERMS", "2020-01-01"), ("alice", "PRIVACY", "2020-01-01")]
    assert request("/api/analyses", token="alice")[0] == 403


def test_legacy_member_can_still_delete_data_and_withdraw_without_consent(served):
    request, library, store = served
    identifier, _, _, _ = stored_analysis(library, store, "carol", "1")
    assert request("/api/analyses/" + identifier, "DELETE", token="carol")[0] == 200
    assert request("/api/auth/account", "DELETE", token="carol")[0] == 200


def test_delete_is_retryable_after_a_file_failure_and_repeat_safe(served, monkeypatch):
    import shutil
    request, library, store = served
    identifier, job, asset, stage_asset = stored_analysis(library, store, "alice", "1")
    real = shutil.rmtree
    def flaky(path, *args, **kwargs):
        if path.name == job:
            raise OSError("file is locked")
        return real(path, *args, **kwargs)
    monkeypatch.setattr(shutil, "rmtree", flaky)
    status, _, _ = request("/api/analyses/" + identifier, "DELETE", token="alice")
    assert status == 400 and store.owns("alice", identifier) and (library.web / identifier / "record.json").exists()
    monkeypatch.setattr(shutil, "rmtree", real)
    assert request("/api/analyses/" + identifier, "DELETE", token="alice")[0] == 200
    assert not (library.web / identifier).exists() and not (library.root / "jobs" / job).exists()
    assert request("/api/analyses/" + identifier, "DELETE", token="alice")[0] == 404  # already gone and released


def test_owned_record_that_vanished_is_released_by_delete(served):
    request, library, store = served
    identifier, _, _, _ = stored_analysis(library, store, "alice", "1")
    (library.web / identifier / "record.json").unlink()
    assert request("/api/analyses/" + identifier, "DELETE", token="alice")[0] == 200
    assert not store.owns("alice", identifier)
