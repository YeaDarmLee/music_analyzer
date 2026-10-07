"""Opt-in integration against configured MySQL; removes only UUID-named test accounts."""
import hashlib
import json
import os
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from uuid import uuid4

import pytest

from music_analyzer.auth import AuthStore
from music_analyzer.legal import REQUIRED_CONSENTS, RIGHTS_CONFIRMATION_VERSION
from music_analyzer.web_server import WebLibrary, make_handler


@pytest.mark.skipif(os.environ.get("MUSIC_TEST_MYSQL") != "1", reason="Set MUSIC_TEST_MYSQL=1 to test the configured MySQL")
def test_mysql_signup_login_ownership_expiry_and_restart(tmp_path, monkeypatch):
    run = uuid4().hex
    emails = [f"test-{run}-{i}@example.invalid" for i in range(2)]
    class TestStore(AuthStore):
        def throttle(self, address):
            super().throttle("integration-" + run)
    auth = TestStore()
    auth.check()
    library = WebLibrary(tmp_path)
    queued = []
    monkeypatch.setattr(library.executor, "submit", lambda *args: queued.append(args))
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(library, tmp_path, 0, auth=auth))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def request(path, payload=None, cookie=None, raw=None):
        headers = {"X-Requested-With": "MusicAnalyzer", "X-Filename": "test.wav"}
        if cookie:
            headers["Cookie"] = cookie
        data = raw if raw is not None else json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(f"http://127.0.0.1:{server.server_port}" + path, data=data, headers=headers)
        try:
            response = urllib.request.urlopen(req)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read()), response.headers

    try:
        credentials = [{"email": email, "password": "test-password-" + run, "display_name": f"Test {i}",
                        "consents": dict(REQUIRED_CONSENTS)} for i, email in enumerate(emails)]
        cookies, users = [], []
        for data in credentials:
            status, result, headers = request("/api/auth/register", data)
            assert status == 201
            assert "password_hash" not in result["user"]
            assert "HttpOnly" in headers["Set-Cookie"] and "SameSite=Strict" in headers["Set-Cookie"]
            cookies.append(headers["Set-Cookie"].split(";")[0])
            users.append(result["user"])
        assert request("/api/auth/register", credentials[0])[0] == 409
        assert request("/api/auth/register", {**credentials[0], "email": f"test-{run}-nc@example.invalid", "consents": {}})[0] == 400
        assert not auth.query("SELECT 1 FROM users WHERE email=%s", (f"test-{run}-nc@example.invalid",))
        assert AuthStore().consents(users[0]["id"]) == dict(REQUIRED_CONSENTS)
        assert auth.has_current_consents(users[0]["id"])
        auth.query("DELETE FROM user_consents WHERE user_id=%s AND consent_type='PRIVACY'", (users[0]["id"],))
        assert not auth.has_current_consents(users[0]["id"])  # legacy-style member: gated
        auth.record_consents(users[0]["id"], dict(REQUIRED_CONSENTS))  # idempotent re-accept
        assert auth.has_current_consents(users[0]["id"])
        assert request("/api/auth/login", {**credentials[0], "password": "wrong-password"})[0] == 401
        status, result, _ = request("/api/analyses?preset=basic_2&rights=" + RIGHTS_CONFIRMATION_VERSION, cookie=cookies[0], raw=b"test audio")
        assert status == 202 and len(queued) == 1
        identifier = result["id"]
        assert AuthStore().owns(users[0]["id"], identifier)  # Survives store/server reconstruction.
        assert not AuthStore().owns(users[1]["id"], identifier)
        assert request("/api/analyses", cookie=cookies[1])[1] == []
        assert request("/api/analyses/" + identifier, cookie=cookies[1])[0] == 404
        assert request("/api/analyses/" + identifier, cookie=cookies[0])[0] == 200
        assert request("/api/auth/logout", {}, cookies[0])[0] == 200
        assert request("/api/auth/me", cookie=cookies[0])[0] == 401
        status, _, headers = request("/api/auth/login", credentials[0])
        assert status == 200
        replacement = headers["Set-Cookie"].split(";")[0]
        assert replacement != cookies[0]
        assert request("/api/auth/me", cookie=replacement)[1]["user"]["id"] == users[0]["id"]
        auth.query("UPDATE sessions SET expires_at=DATE_SUB(UTC_TIMESTAMP(), INTERVAL 1 SECOND) WHERE user_id=%s", (users[0]["id"],))
        assert request("/api/auth/me", cookie=replacement)[0] == 401
        stored = auth.query("SELECT password_hash FROM users WHERE id=%s", (users[0]["id"],))[0]["password_hash"]
        assert stored.startswith("pbkdf2_sha256$") and credentials[0]["password"] not in stored
        auth.assign(users[1]["id"], "analysis_" + "9" * 32)
        auth.delete_account(users[1]["id"])  # sessions, ownership, consents and the user row go together
        for table, column in (("users", "id"), ("sessions", "user_id"), ("analysis_owners", "user_id"), ("user_consents", "user_id")):
            assert not auth.query(f"SELECT 1 FROM {table} WHERE {column}=%s", (users[1]["id"],))
        assert request("/api/auth/me", cookie=cookies[1])[0] == 401
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        library.executor.shutdown()
        for email in emails:
            auth.query("DELETE a FROM analysis_owners a JOIN users u ON u.id=a.user_id WHERE u.email=%s", (email,))
            auth.query("DELETE FROM users WHERE email=%s", (email,))
        auth.query("DELETE FROM auth_attempts WHERE bucket_hash=%s", (hashlib.sha256(("integration-" + run).encode()).hexdigest(),))
