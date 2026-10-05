import io,json,threading,urllib.request,urllib.error
from pathlib import Path
from http.server import ThreadingHTTPServer
import pytest
from music_analyzer.web_server import WebLibrary,make_handler
from music_analyzer.common import write_json

@pytest.fixture
def library(tmp_path):
    lib=WebLibrary(tmp_path)
    yield lib
    lib.executor.shutdown(wait=True)

def test_only_allowed_audio_can_be_uploaded(library):
    with pytest.raises(ValueError,match="MP3"):
        library.create("payload.exe","instrument_roformer_6s",io.BytesIO(b"x"),1)
    with pytest.raises(ValueError,match="1GB"):
        library.create("track.wav","instrument_roformer_6s",io.BytesIO(),0)
    assert not list(library.web.glob("analysis_*"))

def test_path_cannot_escape_data_root(library,tmp_path):
    outside=tmp_path.parent/"outside.txt";outside.write_text("private")
    with pytest.raises(FileNotFoundError):library.safe("../outside.txt")

def test_restart_marks_incomplete_analysis_failed(tmp_path):
    folder=tmp_path/"web"/("analysis_"+"1"*32)
    write_json(folder/"record.json",{"id":folder.name,"state":"RUNNING","stage":"보컬","progress":20})
    lib=WebLibrary(tmp_path)
    try: assert json.loads((folder/"record.json").read_text(encoding="utf-8"))["state"]=="FAILED"
    finally:lib.executor.shutdown()

def test_public_record_omits_local_file_paths(library):
    public=library.public({"name":"song","tracks":[{"path":"private.wav"}],"original":"secret.wav","job_ids":["job"]})
    assert "tracks" not in public and "original" not in public and "job_ids" not in public
    assert public["track_count"]==1

def test_truncated_upload_is_not_enqueued(library):
    with pytest.raises(ValueError,match="중단"):
        library.create("song.wav","instrument_roformer_6s",io.BytesIO(b"x"),100)
    assert not list(library.web.glob("analysis_*/source.wav"))

def test_http_download_range_and_host_guard(library,tmp_path):
    identifier="analysis_"+"2"*32
    wave=tmp_path/"source.wav";wave.write_bytes(b"0123456789")
    row={"id":identifier,"state":"SUCCEEDED","name":"song","created":"now","tracks":[{"family":"guitar","path":"source.wav"}],"original":"source.wav"}
    write_json(library.web/identifier/"record.json",row)
    dist=tmp_path/"dist";dist.mkdir();(dist/"index.html").write_text("<html>Vue</html>")
    server=ThreadingHTTPServer(("127.0.0.1",0),make_handler(library,dist,0))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f"http://127.0.0.1:{server.server_port}"
    try:
        req=urllib.request.Request(base+f"/api/analyses/{identifier}/download/guitar",headers={"Range":"bytes=2-5"})
        with urllib.request.urlopen(req) as response:
            assert response.status==206 and response.read()==b"2345"
            assert response.headers["Content-Range"]=="bytes 2-5/10"
            assert "attachment" in response.headers["Content-Disposition"]
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(urllib.request.Request(base+"/api/analyses",headers={"Host":"evil.example"}))
        assert error.value.code==403
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(base+"/api/missing")
        assert error.value.code==404
    finally:server.shutdown();server.server_close();thread.join()

def test_legacy_instrument_result_uses_selected_vocal_for_playback_and_zip(library):
    import zipfile
    root=library.root
    vocal_id="job_"+"a"*32;instrument_id="job_"+"b"*32
    timeline={"sample_rate":44100,"channels":2,"num_frames":100,"origin_sec":0}
    for asset,name,digest in [("asset_original","song.mp3","original-hash"),("asset_derived","instrumental.wav","accompaniment-hash")]:
        write_json(root/"inputs"/asset/"manifest.json",{"input":{"original_name":name,"sha256":digest}})
        (root/"inputs"/asset/"canonical.wav").write_bytes(b"original")
    vocal_dir=root/"jobs"/vocal_id/"result"
    instrument_dir=root/"jobs"/instrument_id/"result"
    for identifier,asset,folder,model,stems in [
        (vocal_id,"asset_original",vocal_dir,"melband_roformer_kj",
         [{"family":"vocals","path":"stems/vocals.wav","sha256":"selected-vocal"},{"family":"instrumental","path":"stems/instrumental.wav","sha256":"accompaniment-hash"}]),
        (instrument_id,"asset_derived",instrument_dir,"bs_roformer_6s",
         [{"family":family,"path":"stems/"+family+".wav","sha256":"secondary-"+family} for family in ("vocals","drums","bass","guitar","piano","other")])]:
        write_json(folder.parent/"job.json",{"job_id":identifier,"state":"SUCCEEDED","created_at_utc":"today","requested_preset":"test"})
        write_json(folder/"manifest.json",{"job_id":identifier,"asset_id":asset,"source_sha256":"original-canonical" if identifier==vocal_id else "derived-canonical",
                                          "model":{"model_id":model},"timeline":timeline,"stems":stems})
        for stem in stems:
            path=folder/stem["path"];path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(("selected" if identifier==vocal_id else "secondary").encode())
    row=library.get(instrument_id)
    assert row["name"]=="song"
    assert row["vocal_source"]=="roformer" and row["secondary_vocals_excluded"]
    assert len(row["tracks"])==6
    assert library.track_path(row,"vocals")==vocal_dir/"stems/vocals.wav"
    assert library.track_path(row,"guitar")==instrument_dir/"stems/guitar.wav"
    assert vocal_id not in [r["id"] for r in library.entries()]
    with zipfile.ZipFile(library.archive(row)) as archive:
        assert archive.read("vocals.wav")==b"selected"
        assert archive.read("guitar.wav")==b"secondary"

def test_preview_cache_changes_when_vocal_source_changes(library):
    original={"tracks":[{"family":"vocals","path":"old.wav","sha256":"old"}]}
    selected={"tracks":[{"family":"vocals","path":"selected.wav","sha256":"new"}]}
    assert library.fingerprint(original)!=library.fingerprint(selected)

def test_enhanced_preserves_timeline_and_zero_strength(library):
    import numpy as np
    import soundfile as sf
    audio=np.column_stack([np.sin(np.arange(44100)*2*np.pi*300/44100)*.2]*2).astype("float32")
    source=library.root/"raw.wav";sf.write(source,audio,44100,subtype="FLOAT")
    row={"id":"test","tracks":[{"family":"vocals","path":"raw.wav","peak":.2}],"original":"raw.wav"}
    bypass=library.enhanced(row,"vocals",0);corrected=library.enhanced(row,"vocals",50)
    zero,rate=sf.read(bypass,dtype="float32");processed,_=sf.read(corrected,dtype="float32")
    assert rate==44100 and processed.shape==audio.shape
    np.testing.assert_allclose(zero,audio,atol=1e-7)
    assert np.sqrt(np.mean(processed[2000:]**2))<np.sqrt(np.mean(audio[2000:]**2))
    assert sf.info(corrected).subtype=="FLOAT"
    with pytest.raises(ValueError):library.enhanced(row,"vocals",101)
    with pytest.raises(ValueError):library.enhanced(row,"original",50)

def test_bundle_uses_snapshot_strength_and_keeps_raw(library):
    import numpy as np
    import soundfile as sf
    import zipfile
    source=library.root/"raw.wav";sf.write(source,np.zeros((100,2)),44100,subtype="FLOAT")
    row={"id":"bundle","tracks":[{"family":"guitar","path":"raw.wav"}],"original":"raw.wav"}
    with zipfile.ZipFile(library.bundle(row,"both",{"guitar":73})) as archive:
        assert set(archive.namelist())=={"clarity/guitar-clarity-73.wav","raw/guitar.wav","settings.json"}
        assert archive.read("raw/guitar.wav")==source.read_bytes()
        assert b'73' in archive.read("settings.json")
    with pytest.raises(ValueError):library.bundle(row,"both",{"original":50})
    with pytest.raises(ValueError):library.bundle(row,"both",{"guitar":101})
