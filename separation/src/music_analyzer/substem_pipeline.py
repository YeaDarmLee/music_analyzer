"""Full-length secondary separation using existing canonical parent tracks."""
import math,subprocess,threading
from pathlib import Path
from uuid import uuid4
import numpy as np
import soundfile as sf
from .common import project_root,sha256_file,write_json,read_json
from .audio import RATE,write_raw
from .substem_experiment import folder


def prepare_full(root,source,family):
    source=Path(source);digest=sha256_file(source)
    audio,rate=sf.read(source,dtype="float32",always_2d=True)
    if family not in ("guitar","other") or rate!=RATE or audio.ndim!=2 or audio.shape[1]!=2 or not 0<len(audio)<=RATE*900 or not np.isfinite(audio).all():raise ValueError("Invalid full-length parent")
    identifier="experiment_"+uuid4().hex;out=folder(root,identifier);write_raw(out/"input.wav",audio)
    if sha256_file(source)!=digest:raise ValueError("Parent changed")
    write_json(out/"manifest.json",{"schema_version":1,"experiment_id":identifier,"state":"PREPARED","parent_family":family,"parent_path":str(source.resolve()),"parent_sha256":digest,"input_sha256":sha256_file(out/"input.wav"),"timeline":{"sample_rate":RATE,"channels":2,"num_frames":len(audio),"start_frame":0},"quality_improvement_verified":False,"model_inference_performed":False})
    return identifier,len(audio)


def split_clapsep(root,source,family,progress,stopping):
    identifier,frames=prepare_full(root,source,family);python=project_root()/"data/separation/tools/clapsep-env/Scripts/python.exe"
    if not python.is_file():raise ValueError("CLAPSep 환경 준비가 필요합니다: scripts/prepare-clapsep.py")
    positive="A sustained synthesizer pad playing in the background" if family=="other" else "An electric lead guitar playing a melodic solo"
    negative="Electric guitar, piano, drums and singing" if family=="other" else "Rhythm guitar strumming chords"
    command=[str(python),"-m","music_analyzer.clapsep_experiment","--experiment-id",identifier,"--data-root",str(root),"--positive",positive,"--negative",negative,"--no-library"]
    total=math.ceil(((frames*32000+44099)//44100+320000)/160000)
    for retry in range(120):
        if stopping.is_set():raise ValueError("Server stopping")
        process=subprocess.Popen(command,cwd=project_root(),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding="utf-8",errors="replace",creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        log=[]
        def terminate_on_stop():
            while process.poll() is None:
                if stopping.wait(.5):process.terminate();return
        watcher=threading.Thread(target=terminate_on_stop,daemon=True);watcher.start()
        for line in process.stdout:
            log.append(line)
            if line.startswith("completed chunk "):progress(min(1,int(line.split()[-1])/total))
        process.wait();watcher.join(timeout=1)
        (folder(root,identifier)/"worker.log").write_text("".join(log),encoding="utf-8")
        if process.returncode==0:break
        if "filelock" in "".join(log) and "Timeout" in "".join(log):stopping.wait(2);continue
        raise ValueError("CLAPSep failed; see "+str(folder(root,identifier)/"worker.log"))
    else:raise ValueError("GPU busy")
    result=read_json(folder(root,identifier)/"manifest.json")
    if not result.get("model_inference_performed") or result["state"]!="CANDIDATE_READY":raise ValueError("Missing inference result")
    labels=("synth_pad","other_residual") if family=="other" else ("lead_guitar","guitar_residual")
    return [{"family":label,"parent_family":family,"path":str((folder(root,identifier)/(role+".wav")).relative_to(root)),"sha256":sha256_file(folder(root,identifier)/(role+".wav")),"derivation":"model_estimate" if role=="target" else "input_minus_model_estimate"} for label,role in zip(labels,("target","residual"))]
