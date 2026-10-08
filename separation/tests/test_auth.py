import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from music_analyzer.auth import AuthStore, AuthError, DatabaseUnavailable, password_hash, password_matches
from music_analyzer.common import write_json
from music_analyzer.legal import RIGHTS_CONFIRMATION_VERSION
from music_analyzer.web_server import WebLibrary, make_handler


class MemoryAccounts:
    secure_cookie = False

    def __init__(self):
        self.sessions = {"alice": {"id": "alice"}, "bob": {"id": "bob"}}
        self.owners = {}

    def session_user(self, token):
        return self.sessions.get(token)

    def owns(self, user_id, identifier):
        return self.owners.get(identifier) == user_id

    def owned_ids(self, user_id):
        return {key for key, owner in self.owners.items() if owner == user_id}

    def assign(self, user_id, identifier):
        assert identifier not in self.owners
        self.owners[identifier] = user_id

    def logout(self, token):
        self.sessions.pop(token, None)

    def has_current_consents(self, user_id):
        return True

    def release(self, identifier):
        self.owners.pop(identifier, None)

    def delete_account(self, user_id):
        self.sessions.pop(user_id, None)
        for key in self.owned_ids(user_id):
            self.owners.pop(key)


UPLOAD = "/api/analyses?preset=basic_2&rights=" + RIGHTS_CONFIRMATION_VERSION


@pytest.fixture
def tenant_server(tmp_path, monkeypatch):
    library = WebLibrary(tmp_path)
    accounts = MemoryAccounts()
    ids = ["analysis_" + value * 32 for value in "123"]
    for identifier, owner in zip(ids, ("alice", "bob", None)):
        path = tmp_path / (identifier + ".wav")
        path.write_bytes(b"0123456789")
        write_json(library.web / identifier / "record.json", {
            "id": identifier, "name": owner or "legacy", "created": "now", "state": "SUCCEEDED", "duration": 1,
            "tracks": [{"family": "vocals", "path": path.name}], "original": path.name,
        })
        if owner:
            accounts.assign(owner, identifier)
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("studio")
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(library, dist, 0, auth=accounts))
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()

    def request(path, token="alice", method="GET", body=None, headers=None):
        actual_headers = {"X-Requested-With": "MusicAnalyzer"}
        if token:
            actual_headers["Cookie"] = "music_session=" + token
        actual_headers.update(headers or {})
        req = urllib.request.Request(f"http://127.0.0.1:{server.server_port}" + path,
                                     data=body, method=method, headers=actual_headers)
        try:
            response = urllib.request.urlopen(req)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, response.read(), response.headers

    yield request, library, accounts, ids
    server.shutdown()
    server.server_close()
    worker.join()
    library.executor.shutdown()


def test_passwords_are_salted_and_verified():
    first = password_hash("correct-password")
    second = password_hash("correct-password")
    assert first != second and "correct-password" not in first
    assert password_matches("correct-password", first)
    assert not password_matches("incorrect-password", first)
    assert not password_matches("correct-password", "malformed")


def test_only_current_members_analyses_are_listed(tenant_server):
    request, _, _, ids = tenant_server
    for token, identifier in zip(("alice", "bob"), ids):
        status, body, _ = request("/api/analyses", token)
        assert status == 200
        assert [row["id"] for row in json.loads(body)] == [identifier]


@pytest.mark.parametrize("suffix", ["", "/audio/vocals", "/audio/original", "/audio/vocals?start_frame=0&num_frames=100", "/download/vocals", "/download/original", "/archive"])
def test_other_members_and_legacy_results_are_inaccessible(tenant_server, suffix):
    request, _, _, ids = tenant_server
    for identifier in ids[1:]:
        status, body, _ = request("/api/analyses/" + identifier + suffix)
        assert status == 404 and "찾을 수" in json.loads(body)["error"]
    assert request("/api/analyses/" + ids[0] + suffix, token=None)[0] == 401


def test_authenticated_download_range_and_logout(tenant_server):
    request, _, accounts, ids = tenant_server
    status, body, headers = request("/api/analyses/" + ids[0] + "/download/vocals", headers={"Range": "bytes=2-5"})
    assert status == 206 and body == b"2345"
    assert headers["Cache-Control"] == "private, no-store"
    status, _, headers = request("/api/auth/logout", method="POST", body=b"{}")
    assert status == 200 and "Max-Age=0" in headers["Set-Cookie"]
    assert "alice" not in accounts.sessions
    assert request("/api/analyses")[0] == 401


def test_mutations_require_session_ownership_and_csrf_header(tenant_server):
    request, _, _, ids = tenant_server
    route = "/api/analyses/" + ids[1] + "/vocal-detail"
    assert request(route, method="POST", body=b"{}")[0] == 404
    assert request(route, token=None, method="POST", body=b"{}")[0] == 401
    assert request("/api/auth/logout", method="POST", headers={"X-Requested-With": ""})[0] == 403
    assert request("/api/auth/logout", method="POST", headers={"Origin": "https://other.example"})[0] == 403
    assert request("/api/analyses", token=None, method="POST", body=b"audio")[0] == 401


def test_owner_is_saved_before_analysis_is_enqueued(tenant_server, monkeypatch):
    request, library, accounts, _ = tenant_server
    calls = []
    def submit(fn, folder, source, row):
        assert accounts.owns("alice", row["id"])
        calls.append(row["id"])
    monkeypatch.setattr(library.executor, "submit", submit)
    status, body, _ = request(UPLOAD, method="POST", body=b"audio", headers={"X-Filename": "my.wav"})
    assert status == 202 and calls == [json.loads(body)["id"]]
    assert request("/api/analyses/" + calls[0], "bob")[0] == 404


def test_database_failure_never_enqueues_analysis(tenant_server, monkeypatch):
    request, library, accounts, _ = tenant_server
    calls = []
    monkeypatch.setattr(library.executor, "submit", lambda *args: calls.append(args))
    def fail(*args):
        raise DatabaseUnavailable("DB unavailable")
    monkeypatch.setattr(accounts, "assign", fail)
    assert request(UPLOAD, method="POST", body=b"audio", headers={"X-Filename": "my.wav"})[0] == 503
    assert calls == []


def test_child_analysis_inherits_parent_owner_and_reuses_only_owned_jobs(tenant_server, monkeypatch):
    from music_analyzer import registry
    request, library, accounts, ids = tenant_server
    monkeypatch.setattr(registry, "resolve", lambda *args: None)
    # An old unowned child must not be returned as if the requesting member owned it.
    hidden = "analysis_" + "4" * 32
    write_json(library.web / hidden / "record.json", {
        "id": hidden, "parent_analysis_id": ids[0], "model": "bs_karaoke",
        "created": "now", "state": "QUEUED", "tracks": [],
    })
    queued = []
    def submit(fn, folder, source, row):
        assert accounts.owns("alice", row["id"])
        queued.append(row["id"])
    monkeypatch.setattr(library.executor, "submit", submit)
    route = "/api/analyses/" + ids[0] + "/vocal-detail"
    status, body, _ = request(route, method="POST", body=b"{}")
    child = json.loads(body)["id"]
    assert status == 202 and child != hidden and queued == [child]
    assert request("/api/analyses/" + child, "bob")[0] == 404
    assert json.loads(request(route, method="POST", body=b"{}")[1])["id"] == child
    assert queued == [child]


def test_invalid_credentials_are_rejected_before_sql():
    store = AuthStore({})
    for data in ([], {}, {"email": "invalid", "password": "long-password"}, {"email": "a@b.com", "password": "short"}):
        with pytest.raises(AuthError):
            store.credentials(data)
