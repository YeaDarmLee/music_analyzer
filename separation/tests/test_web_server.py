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

def test_silent_output_is_hidden_but_quiet_and_brief_audio_remain(library):
    import numpy as np
    import soundfile as sf
    folder=library.web/("analysis_"+"e"*32);folder.mkdir()
    tracks=[]
    for family,audio in (("piano",np.zeros((44100,2),dtype=np.float32)),
                         ("synth",np.full((44100,2),.0001,dtype=np.float32)),
                         ("guitar",np.pad(np.full((1,2),.005,dtype=np.float32),((0,44099),(0,0))))):
        path=folder/(family+".wav");sf.write(path,audio,44100,subtype="FLOAT")
        tracks.append(library.track_activity({"family":family,"path":str(path.relative_to(library.root))}))
    assert [t["silent"] for t in tracks]==[True,False,False]
    original=folder/"original.wav";sf.write(original,np.ones((44100,2),dtype=np.float32)*.1,44100,subtype="FLOAT")
    row={"id":folder.name,"state":"SUCCEEDED","tracks":tracks,"original":str(original.relative_to(library.root))}
    write_json(folder/"record.json",row)
    detail=library.detail(folder.name)
    assert [t["family"] for t in detail["tracks"]]==["synth","guitar"]
    assert detail["track_count"]==library.public(row)["track_count"]==2
    assert library.track_path(row,"piano").exists()  # Raw data remains available.

@pytest.mark.parametrize("family",["lead","backing","piano","synth","strings","brass","acoustic_guitar","guitar","bass","drums","other"])
def test_near_silence_rechecks_all_completed_families(library,family):
    leakage={"family":family,"peak":.00135701,"signal_rms":.0000333421,"silent":False}
    assert library.track_activity(leakage)["silent"]
    assert library.public({"tracks":[leakage]})["track_count"]==0
    assert not library.track_activity({**leakage,"peak":.005})["silent"]  # Brief real note.
    assert not library.track_activity({**leakage,"signal_rms":.0001})["silent"]  # Quiet sustained note.


def test_flat_session_keeps_instrument_parents_and_reconstructs_remaining(library):
    import numpy as np
    import soundfile as sf
    identifier="analysis_"+"f"*32
    folder=library.web/identifier;folder.mkdir()
    families=["vocals","lead","backing","piano","other","guitar","bass","drums","synth_pad","other_residual","lead_guitar","guitar_residual"]
    tracks=[]
    for i,family in enumerate(families):
        path=folder/(family+".wav")
        sf.write(path,np.full((100,2),.01*(i+1)),44100,subtype="FLOAT")
        tracks.append({"family":family,"path":str(path.relative_to(library.root)),"parent_family":"vocals" if family in ("lead","backing") else None})
    original=folder/"original.wav";sf.write(original,np.ones((100,2))*.8,44100,subtype="FLOAT")
    row={"id":identifier,"tracks":tracks,"original":str(original.relative_to(library.root)),"groups":[{}]}
    result=library.flatten_session(row)
    assert [t["family"] for t in result["tracks"]]==["lead","backing","piano","synth","guitar","bass","drums","other"]
    assert "groups" not in result and all("parent_family" not in t for t in result["tracks"])
    assert library.track_path(result,"synth")==folder/"other.wav"
    assert library.track_path(result,"guitar")==folder/"guitar.wav"
    summed=sum(sf.read(library.track_path(result,t["family"]))[0] for t in result["tracks"])
    np.testing.assert_allclose(summed,sf.read(original)[0],atol=1e-7)

def test_path_cannot_escape_data_root(library,tmp_path):
    outside=tmp_path.parent/"outside.txt";outside.write_text("private")
    with pytest.raises(FileNotFoundError):library.safe("../outside.txt")

def test_final_ten_tracks_reconstruct_instrumental_without_subtracting_vocals(library):
    import numpy as np
    import soundfile as sf
    identifier="analysis_"+"d"*32
    folder=library.web/identifier;folder.mkdir()
    labels=["vocals","lead","backing","piano","synth","bowed_strings","brass","acoustic-guitar","electric-guitar","bass","drums","other"]
    tracks=[]
    for index,label in enumerate(labels):
        path=folder/(label+".wav")
        sf.write(path,np.full((200,2),.02*(index+1)),44100,subtype="FLOAT")
        tracks.append({"family":label,"path":str(path.relative_to(library.root))})
    original=folder/"original.wav";sf.write(original,np.full((200,2),.9),44100,subtype="FLOAT")
    row={"id":identifier,"tracks":tracks,"original":str(original.relative_to(library.root))}
    instrumental=folder/"instrumental.wav";sf.write(instrumental,np.full((200,2),.7),44100,subtype="FLOAT")
    row["instrumental"]=str(instrumental.relative_to(library.root))
    result=library.final_session(row)
    assert [t["family"] for t in result["tracks"]]==["lead","backing","piano","synth","strings","brass","acoustic_guitar","guitar","bass","drums","other"]
    assert result["track_layout"]=="flat_v4" and "track_note" not in result
    assert library.track_path(result,"strings")==folder/"bowed_strings.wav"
    assert library.track_path(result,"synth")==folder/"synth.wav"
    summed=sum(sf.read(library.track_path(result,t["family"]))[0] for t in result["tracks"] if t["family"] not in ("lead","backing"))
    np.testing.assert_allclose(summed,sf.read(instrumental)[0],atol=1e-7)
    with pytest.raises(ValueError,match="누락"):
        library.final_session({**row,"tracks":[t for t in tracks if t["family"]!="synth"]})
    for family in ("strings","brass","acoustic_guitar"):
        enhanced=library.enhanced(result,family,0)
        np.testing.assert_array_equal(sf.read(enhanced)[0],sf.read(library.track_path(result,family))[0])

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
    class OwnerSession:
        def session_user(self,token):return {"id":"test-owner"}
        def owns(self,user_id,analysis_id):return analysis_id==identifier
    server=ThreadingHTTPServer(("127.0.0.1",0),make_handler(library,dist,0,auth=OwnerSession()))
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

def test_vocal_detail_queues_parent_vocal_without_changing_parent(library,monkeypatch):
    import copy
    import music_analyzer.registry as registry
    parent={"id":"analysis_"+"a"*32,"name":"song","state":"SUCCEEDED","duration":20,"tracks":[{"family":"vocals","path":"vocals.wav"}]}
    original=copy.deepcopy(parent);(library.root/"vocals.wav").write_bytes(b"audio")
    monkeypatch.setattr(library,"get",lambda identifier:parent)
    monkeypatch.setattr(registry,"resolve",lambda *args:(None,None))
    calls=[];monkeypatch.setattr(library.executor,"submit",lambda *args:calls.append(args))
    result=library.create_vocal_detail(parent["id"])
    assert parent==original and result["state"]=="QUEUED"
    assert result["parent_analysis_id"]==parent["id"] and calls[0][2]==library.root/"vocals.wav"
    assert not result["quality_improvement_verified"]


def test_vocal_detail_rejects_unknown_model(library):
    with pytest.raises(ValueError,match="지원하지 않는"):
        library.create_vocal_detail("unused",preset="unknown")

def test_long_preview_is_lossless_compressed_and_preserves_timeline(library):
    import numpy as np
    import soundfile as sf
    samples=np.linspace(-.4,.4,4096,dtype=np.float32)
    stereo=np.column_stack((samples,-samples))
    source=library.root/'source.wav'
    sf.write(source,stereo,44100,subtype='FLOAT')
    row={'id':'analysis_'+'e'*32,'duration':121,'original':'source.wav','tracks':[{'family':'guitar','path':'source.wav','peak':.4}]}
    target=library.preview(row,'guitar')
    actual,rate=sf.read(target,always_2d=True)
    assert target.suffix=='.flac' and sf.info(target).format=='FLAC'
    assert rate==44100 and actual.shape==stereo.shape
    np.testing.assert_allclose(actual,stereo*.9,atol=1/32768)
    assert library.preview(row,'guitar')==target
    assert library.track_path(row,'guitar')==source

def test_audio_window_preserves_samples_timeline_and_bounds(library):
    import numpy as np
    import soundfile as sf
    samples=np.column_stack((np.linspace(-.4,.4,4096,dtype=np.float32),np.zeros(4096,dtype=np.float32)))
    source=library.root/'source.wav';sf.write(source,samples,44100,subtype='FLOAT');before=source.read_bytes()
    row={'id':'analysis_'+'f'*32,'duration':121,'original':'source.wav','tracks':[{'family':'guitar','path':'source.wav','peak':.4}]}
    body=library.audio_window(row,'guitar',2048,4096)
    actual,rate=sf.read(io.BytesIO(body),always_2d=True)
    assert rate==44100 and actual.shape==(2048,2)
    np.testing.assert_allclose(actual,samples[2048:]*.9,atol=1/32768)
    assert source.read_bytes()==before
    for start,count in [(-1,1),(0,1323001),(4096,1),(0,0)]:
        with pytest.raises(ValueError):library.audio_window(row,'guitar',start,count)
