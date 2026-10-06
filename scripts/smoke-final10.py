"""Real GPU pipeline check in an isolated study library, without account mutations."""
import os
import time
from pathlib import Path
import soundfile as sf
from music_analyzer.common import project_root,read_json,write_json
from music_analyzer.registry import paths,config
from music_analyzer.web_server import WebLibrary

project=project_root()
root=project/"data/part-studies/final10-smoke"
root.mkdir(parents=True,exist_ok=True)
for model_id in ("melband_roformer_kj","bs_roformer_6s","bs_karaoke","bs_roformer_mega5"):
    checkpoint,registration=paths(project/"data/separation",model_id)
    folder=root/"models"/model_id;folder.mkdir(parents=True,exist_ok=True)
    if not (folder/checkpoint.name).exists():os.link(checkpoint,folder/checkpoint.name)
    write_json(folder/"registration.json",read_json(registration))
source=project/"data/reset-backups/reset-20261006-193853/inputs/asset_d8b1327923bd43c98a4cca041db58c25/canonical.wav"
with sf.SoundFile(source) as handle:
    handle.seek(8*44100);audio=handle.read(20*44100,dtype="float32",always_2d=True)
clip=root/"orange-8-28.wav";sf.write(clip,audio,44100,subtype="FLOAT")
library=WebLibrary(root)
try:
    with clip.open("rb") as stream:row=library.create(clip.name,"final_10",stream,clip.stat().st_size)
    stage=None
    progress_samples=[]
    while True:
        record=library.get(row["id"])
        progress_samples.append({"stage":record["stage"],"progress":record["progress"],"state":record["state"]})
        assert record["state"]=="SUCCEEDED" or record["progress"]<100
        if record["stage"]!=stage:
            stage=record["stage"];print(stage,flush=True)
        if record["state"] in ("SUCCEEDED","FAILED","CANCELLED"):break
        time.sleep(1)
    assert record["state"]=="SUCCEEDED",record.get("error")
    assert all(a['progress']<=b['progress'] for a,b in zip(progress_samples,progress_samples[1:]))
    jobs=[read_json(root/"jobs"/identifier/"job.json") for identifier in record["job_ids"]]
    assert jobs[1]["asset_id"]==jobs[2]["asset_id"]!=jobs[0]["asset_id"]
    assert record["synth_recovery"]["negative"]=="piano, acoustic guitar strumming, electric guitar, bass and drums"
    assert record["synth_recovery"]["instrumental_max_abs_error"]<2e-6
    assert record["strings_recovery"]["instrumental_max_abs_error"]<2e-6
    families=[t["family"] for t in record["tracks"]]
    assert families==["lead","backing","piano","synth","strings","brass","acoustic_guitar","guitar","bass","drums","other"]
    import numpy as np,zipfile
    reconstructed=np.zeros_like(audio,dtype=np.float64)
    for family in families:
        track,rate=sf.read(library.track_path(record,family),dtype="float32",always_2d=True)
        assert track.shape==audio.shape and rate==44100 and np.isfinite(track).all()
        if family not in ("lead","backing"):reconstructed+=track
    instrumental,_=sf.read(root/record["instrumental"],dtype="float32",always_2d=True)
    np.testing.assert_allclose(reconstructed,instrumental,atol=2e-7)
    with zipfile.ZipFile(library.archive(record)) as archive:assert {f+".wav" for f in families}.issubset(archive.namelist())
    write_json(root/"verification.json",{"state":"passed","analysis_id":row["id"],"families":families,"frames":len(audio),"reconstruction_max_abs":float(np.max(np.abs(reconstructed-instrumental))),"progress_samples":progress_samples})
    print("FINAL TEN TRACKS VERIFIED",flush=True)
finally:
    library.executor.shutdown(wait=True)
