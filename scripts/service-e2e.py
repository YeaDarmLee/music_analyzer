"""Service end-to-end against a RUNNING server (localhost): throw-away account -> consent -> upload -> commercial analysis -> playback preview
-> single WAV -> full ZIP -> ZIP temp gone -> analysis delete -> account delete. Leaves the DB and the data root as it found them.

usage: service-e2e.py [preset=commercial_6] [base=http://localhost:8780]     (the server must run with MUSIC_RELEASE_PROFILE=commercial)
Credentials are random per run, only used against the local server, and the account is deleted at the end.
"""
import io, json, re, secrets, sys, time, urllib.error, urllib.request, zipfile
from pathlib import Path
import numpy as np, soundfile as sf
from music_analyzer.auth import AuthStore
from music_analyzer.common import project_root
from music_analyzer.legal import REQUIRED_CONSENTS, RIGHTS_CONFIRMATION_VERSION

preset = sys.argv[1] if len(sys.argv) > 1 else "commercial_6"; base_url = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8780"
root = project_root(); data = root / "data/separation"
EXPECTED = {"commercial_2": 2, "commercial_6": 6, "commercial_13": 13}[preset]
INTERNAL = re.compile(r"RoFormer|Mega\s?53|\bKJ\b|CLAPSep|core4|mega5|mega7|melband|bs_roformer", re.I)
cookie = None


def call(path, method="GET", payload=None, raw=None, headers=None):
    h = {"X-Requested-With": "MusicAnalyzer", **(headers or {})}
    if cookie:
        h["Cookie"] = cookie
    body = raw if raw is not None else json.dumps(payload).encode() if payload is not None else None
    if payload is not None:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(base_url + path, data=body, headers=h, method=method)
    try:
        response = urllib.request.urlopen(req)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        return response.status, response.read(), response.headers


def js(path, *a, **k):
    status, body, headers = call(path, *a, **k)
    return status, json.loads(body), headers


files = lambda sub: sorted(p.relative_to(data).as_posix() for p in (data / sub).rglob("*") if p.is_file()) if (data / sub).exists() else []
store = AuthStore(); users_before = store.query("SELECT COUNT(*) c FROM users")[0]["c"]
steps = {}
email = f"e2e-{secrets.token_hex(6)}@example.invalid"; password = secrets.token_urlsafe(18); user_id = None
try:
    status, release, _ = js("/api/release")
    steps["release"] = {"profile": release["profile"], "presets": release["presets"]}
    assert release["profile"] == "commercial" and preset in release["presets"], release
    assert not any(p.startswith(("basic_", "final_")) for p in release["presets"])

    # existing members must be asked for consent again (user_consents was cleared by the reset)
    steps["existing_members_need_consent"] = all(not store.has_current_consents(r["id"]) for r in store.query("SELECT id FROM users WHERE email NOT LIKE %s", ("e2e-%@example.invalid",)))

    status, result, headers = js("/api/auth/register", "POST", {"email": email, "password": password, "display_name": "E2E", "consents": dict(REQUIRED_CONSENTS)})
    assert status == 201, (status, result)
    cookie = headers["Set-Cookie"].split(";")[0]; user_id = result["user"]["id"]
    steps["signup"] = status
    assert js("/api/auth/me")[1]["user"]["id"] == user_id

    # analysis without current consent must be refused: drop this account's consents, try, then restore
    store.query("DELETE FROM user_consents WHERE user_id=%s", (user_id,))
    refused = js(f"/api/analyses?preset={preset}&rights={RIGHTS_CONFIRMATION_VERSION}", "POST", raw=b"x", headers={"X-Filename": "a.wav"})[0]
    steps["upload_without_consent_status"] = refused; assert refused in (401, 403), refused
    assert js("/api/auth/consent", "POST", {"consents": dict(REQUIRED_CONSENTS)})[0] == 200

    clip = io.BytesIO(); sf.write(clip, sf.read(root / "separation/tests/fixtures/synthetic-mix-15s.wav", dtype="float32", always_2d=True)[0][: 44100 * 8], 44100, format="WAV", subtype="PCM_16")
    no_rights = js(f"/api/analyses?preset={preset}", "POST", raw=clip.getvalue(), headers={"X-Filename": "e2e.wav"})[0]
    steps["upload_without_rights_status"] = no_rights; assert no_rights == 400
    dev = js(f"/api/analyses?preset=basic_6&rights={RIGHTS_CONFIRMATION_VERSION}", "POST", raw=clip.getvalue(), headers={"X-Filename": "e2e.wav"})
    steps["development_preset_refused"] = [dev[0], dev[1].get("error")]; assert dev[0] == 400
    status, row, _ = js(f"/api/analyses?preset={preset}&rights={RIGHTS_CONFIRMATION_VERSION}", "POST", raw=clip.getvalue(), headers={"X-Filename": "e2e.wav"})
    assert status == 202, (status, row)
    identifier = row["id"]; started = time.monotonic(); progress = []
    while True:
        status, row, _ = js(f"/api/analyses/{identifier}")
        if not progress or progress[-1] != row["state"]:
            progress.append(row["state"])
        if row["state"] in ("SUCCEEDED", "FAILED", "CANCELLED") or time.monotonic() - started > 1800:
            break
        time.sleep(1)
    assert row["state"] == "SUCCEEDED", row
    families = sorted(t["family"] for t in row["tracks"])
    steps["analysis"] = {"states": progress, "seconds": round(time.monotonic() - started), "stems": len(families), "families": families}
    assert 0 < len(families) <= EXPECTED, families  # the API lists audible stems only; the final/ folder must hold every stem of the contract
    steps["api_detail_keys"] = sorted(row)
    leak = INTERNAL.search(json.dumps(row, ensure_ascii=False)); assert not leak, json.dumps(row, ensure_ascii=False)[max(0, leak.start() - 80): leak.end() + 60]

    folder = data / "web" / identifier
    steps["layout"] = {"top": sorted(p.name for p in folder.iterdir()), "final": sorted(p.name for p in (folder / "final").iterdir())}
    assert (folder / "original.wav").is_file() and (folder / "manifest.json").is_file() and len(steps["layout"]["final"]) == EXPECTED
    steps["scratch_after_success"] = {"jobs": files("jobs"), "inputs": files("inputs")}
    scratch = steps["scratch_after_success"]["jobs"] + steps["scratch_after_success"]["inputs"]
    audio_left = [f for f in scratch if f.endswith((".wav", ".flac", ".mp3", ".zip", ".npy", ".pt", ".ckpt")) or (data / f).stat().st_size > 1 << 20]
    steps["scratch_after_success"] = {"trace_files": len(scratch), "trace_bytes": sum((data / f).stat().st_size for f in scratch), "audio_or_large_left": audio_left}
    assert audio_left == [], audio_left  # job.json / attempt logs / request / environment are the kept trace; no audio

    family = families[0]
    status, body, headers = call(f"/api/analyses/{identifier}/audio/{family}?start_frame=0&num_frames=44100")
    steps["preview"] = {"status": status, "frames": len(sf.read(io.BytesIO(body))[0])}; assert status == 200
    status, body, headers = call(f"/api/analyses/{identifier}/download/{family}")
    audio, rate = sf.read(io.BytesIO(body), dtype="float32", always_2d=True)
    steps["single_wav"] = {"status": status, "family": family, "seconds": round(len(audio) / rate, 2), "finite": bool(np.isfinite(audio).all())}
    assert status == 200 and np.isfinite(audio).all()
    status, body, headers = call(f"/api/analyses/{identifier}/archive")
    names = sorted(zipfile.ZipFile(io.BytesIO(body)).namelist())
    steps["zip"] = {"status": status, "entries": len(names), "leftover_zip_files": sorted(p.name for p in (data / "web/archives").glob("*")) if (data / "web/archives").exists() else []}
    assert status == 200 and len(names) >= EXPECTED and steps["zip"]["leftover_zip_files"] == [], steps["zip"]

    # library re-access (second request cycle with the same session)
    assert any(r["id"] == identifier for r in js("/api/analyses")[1])
    assert js(f"/api/analyses/{identifier}")[0] == 200
    status, _, _ = js(f"/api/analyses/{identifier}", "DELETE")
    steps["delete"] = {"status": status, "web_files": files("web"), "owner_rows": store.query("SELECT COUNT(*) c FROM analysis_owners WHERE analysis_id=%s", (identifier,))[0]["c"]}
    assert status == 200 and steps["delete"]["web_files"] == [] and steps["delete"]["owner_rows"] == 0
    assert files("jobs") == [] and files("inputs") == [], (files("jobs"), files("inputs"))
finally:
    if user_id and cookie:
        js("/api/auth/account", "DELETE")
    elif user_id:
        store.delete_account(user_id)
    steps["users_before_after"] = [users_before, store.query("SELECT COUNT(*) c FROM users")[0]["c"]]
    steps["analysis_owner_rows"] = store.query("SELECT COUNT(*) c FROM analysis_owners")[0]["c"]
    steps["web_files_after"] = len(files("web")); steps["jobs_files_after"] = len(files("jobs")); steps["inputs_files_after"] = len(files("inputs"))
    print(json.dumps(steps, ensure_ascii=False, indent=1))
assert steps["users_before_after"][0] == steps["users_before_after"][1] and steps["analysis_owner_rows"] == 0
print("SERVICE E2E OK", preset)
