"""Isolated short-clip experiments; no model inference or quality claim."""
import argparse,math,re
from pathlib import Path
from uuid import uuid4
import numpy as np
import soundfile as sf
from .audio import RATE,write_raw
from .common import project_root,read_json,write_json,sha256_file

def folder(root,identifier):
    if not re.fullmatch(r"experiment_[0-9a-f]{32}",identifier):raise ValueError("Invalid experiment ID")
    return Path(root)/"substems"/identifier

def prepare(root,input_path,task,start=0,duration=20):
    if task not in ("vocals","guitar","other"):raise ValueError("Invalid parent family")
    if not math.isfinite(start) or not math.isfinite(duration) or start<0 or not 1<=duration<=30:raise ValueError("Use a finite 1–30 second clip")
    path=Path(input_path).resolve();digest=sha256_file(path)
    with sf.SoundFile(path) as source:
        if source.samplerate!=RATE or source.channels!=2:raise ValueError("Requires canonical 44.1kHz stereo WAV")
        offset=round(start*RATE);count=round(duration*RATE)
        if offset+count>source.frames:raise ValueError("Requested window exceeds input")
        source.seek(offset);audio=source.read(count,dtype="float32",always_2d=True)
    if not np.isfinite(audio).all():raise ValueError("Non-finite input")
    if sha256_file(path)!=digest:raise ValueError("Source changed while preparing")
    identifier="experiment_"+uuid4().hex;out=folder(root,identifier)
    write_raw(out/"input.wav",audio)
    manifest={"schema_version":1,"experiment_id":identifier,"state":"PREPARED","parent_family":task,
      "parent_path":str(path),"parent_sha256":digest,"input_sha256":sha256_file(out/"input.wav"),
      "timeline":{"sample_rate":RATE,"channels":2,"num_frames":count,"start_frame":offset},
      "quality_improvement_verified":False,"model_inference_performed":False}
    write_json(out/"manifest.json",manifest);return manifest

def publish(root,identifier,estimate,model_id,prompt=""):
    out=folder(root,identifier);manifest=read_json(out/"manifest.json")
    if manifest["state"]!="PREPARED":raise ValueError("Create a new experiment for another estimate")
    if not model_id.strip():raise ValueError("Model provenance is required")
    if sha256_file(out/"input.wav")!=manifest["input_sha256"]:raise ValueError("Experiment input changed")
    parent,rate=sf.read(out/"input.wav",dtype="float32",always_2d=True)
    estimate=Path(estimate).resolve();digest=sha256_file(estimate)
    target,target_rate=sf.read(estimate,dtype="float32",always_2d=True)
    if rate!=target_rate or parent.shape!=target.shape or not np.isfinite(target).all():raise ValueError("Estimate must match timeline and contain finite stereo audio")
    if sha256_file(estimate)!=digest:raise ValueError("Estimate changed while reading")
    residual=(parent-target).astype(np.float32)
    if not np.isfinite(residual).all():raise ValueError("Residual overflow")
    write_raw(out/"target.wav",target);write_raw(out/"residual.wav",residual)
    manifest.update(state="CANDIDATE_READY",model_id=model_id,prompt=prompt,estimate_sha256=digest,
      model_inference_performed=False,estimate_origin="externally_generated",reconstruction_max_abs=float(np.max(np.abs(parent-(target+residual)))),
      outputs=[{"role":role,"path":role+".wav","sha256":sha256_file(out/(role+".wav"))} for role in ("target","residual")])
    write_json(out/"manifest.json",manifest);return manifest

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--data-root",type=Path,default=project_root()/"data/separation")
    sub=parser.add_subparsers(dest="command",required=True)
    prep=sub.add_parser("prepare");prep.add_argument("--input",type=Path,required=True);prep.add_argument("--task",choices=["vocals","guitar","other"],required=True);prep.add_argument("--start",type=float,default=0);prep.add_argument("--duration",type=float,default=20)
    pub=sub.add_parser("publish");pub.add_argument("--experiment-id",required=True);pub.add_argument("--estimate",type=Path,required=True);pub.add_argument("--model-id",required=True);pub.add_argument("--prompt",default="")
    args=parser.parse_args()
    result=prepare(args.data_root,args.input,args.task,args.start,args.duration) if args.command=="prepare" else publish(args.data_root,args.experiment_id,args.estimate,args.model_id,args.prompt)
    import json
    print(json.dumps(result,ensure_ascii=True,indent=2))
if __name__=="__main__":main()
