"""Short-clip AudioSep inference, isolated from the production model environment."""
import argparse, os, subprocess, sys, time
from pathlib import Path
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
from filelock import FileLock
from .common import project_root, read_json, write_json, sha256_file
from .substem_experiment import folder, publish
from .audio import write_raw


def restore_channel(prediction, frames):
    prediction=np.asarray(prediction,dtype=np.float32)
    expected=(frames*32000+44099)//44100
    if prediction.ndim!=1 or len(prediction)!=expected or not np.isfinite(prediction).all():
        raise ValueError("Invalid native model timeline")
    restored=resample_poly(prediction,441,320)
    if len(restored)<frames:raise ValueError("Model output is shorter than source")
    return restored[:frames].astype(np.float32)


def run(root,identifier,prompt,repo):
    if not prompt.strip() or len(prompt)>300:raise ValueError("Use a nonempty prompt of at most 300 characters")
    root=Path(root).resolve();repo=Path(repo).resolve();out=folder(root,identifier)
    manifest=read_json(out/"manifest.json")
    if manifest["state"]!="PREPARED":raise ValueError("A fresh prepared experiment is required")
    if manifest["parent_family"] not in ("other","guitar"):raise ValueError("Use an other or guitar parent")
    registration=read_json(project_root()/"separation/configs/models/audiosep_base.json")
    revision=subprocess.check_output(["git","-c","safe.directory="+str(repo),"rev-parse","HEAD"],cwd=repo,text=True).strip()
    if revision!=registration["code_revision"]:raise ValueError("AudioSep revision changed")
    if subprocess.check_output(["git","-c","safe.directory="+str(repo),"status","--porcelain","--untracked-files=no"],cwd=repo,text=True).strip():raise ValueError("AudioSep upstream files changed")
    for artifact in registration["artifacts"]:
        if sha256_file(repo/"checkpoint"/artifact["filename"])!=artifact["sha256"]:raise ValueError("AudioSep checkpoint changed")
    if sha256_file(out/"input.wav")!=manifest["input_sha256"]:raise ValueError("Experiment input changed")
    source,rate=sf.read(out/"input.wav",dtype="float32",always_2d=True)
    if rate!=44100 or source.shape!=(manifest["timeline"]["num_frames"],2):raise ValueError("Invalid parent timeline")
    started=time.perf_counter();runtime=root/"runtime";runtime.mkdir(exist_ok=True)
    with FileLock(str(runtime/"supervisor.lock"),timeout=0),FileLock(str(runtime/"gpu-execution.lock"),timeout=0):
        old=os.getcwd()
        try:
            os.chdir(repo);sys.path.insert(0,str(repo))
            import torch
            original_load=torch.nn.Module.load_state_dict
            def compatible_load(module,state_dict,*args,**kwargs):
                # Transformers >=4.31 regenerates this non-learned position buffer.
                if module.__class__.__name__=="CLAP" and "text_branch.embeddings.position_ids" in state_dict:
                    state_dict=state_dict.copy();state_dict.pop("text_branch.embeddings.position_ids")
                return original_load(module,state_dict,*args,**kwargs)
            torch.nn.Module.load_state_dict=compatible_load
            from pipeline import build_audiosep
            if not torch.cuda.is_available():raise ValueError("CUDA is required for this experiment")
            torch.manual_seed(0);torch.cuda.reset_peak_memory_stats()
            model=build_audiosep(str(repo/"config/audiosep_base.yaml"),str(repo/"checkpoint/audiosep_base_4M_steps.ckpt"),torch.device("cuda"))
            with torch.inference_mode():
                condition=model.query_encoder.get_query_embed(modality="text",text=[prompt],device="cuda").to("cuda")
                channels=[]
                for channel in range(2):
                    native=resample_poly(source[:,channel],320,441).astype(np.float32)
                    inputs={"mixture":torch.from_numpy(native)[None,None,:].to("cuda"),"condition":condition}
                    prediction=model.ss_model(inputs)["waveform"][0,0].float().cpu().numpy()
                    channels.append(restore_channel(prediction,len(source)))
                    print("channel",channel+1,"complete",flush=True)
            torch.cuda.synchronize();memory=torch.cuda.max_memory_allocated()
        finally:
            if "original_load" in locals():torch.nn.Module.load_state_dict=original_load
            os.chdir(old)
    estimate=out/"audiosep-estimate.wav";write_raw(estimate,np.column_stack(channels))
    result=publish(root,identifier,estimate,"audiosep_base",prompt)
    result.update(model_inference_performed=True,estimate_origin="audiosep_independent_channel_inference",model=registration,wall_sec=time.perf_counter()-started,peak_allocated_bytes=memory,channel_strategy="independent inference; stereo consistency needs listening",resampling={"input_rate":44100,"model_rate":32000,"output_rate":44100,"alignment":"polyphase; output tail trimmed to exact parent frames"})
    write_json(out/"manifest.json",result)
    return result


def add_to_library(root,result):
    """Expose only completed inference results to the existing player."""
    from uuid import uuid4
    root=Path(root).resolve();out=folder(root,result["experiment_id"])
    if result["state"]!="CANDIDATE_READY" or not result.get("model_inference_performed"):raise ValueError("Inference result required")
    family=result["parent_family"]
    labels=("synth_pad","other_residual") if family=="other" else ("lead_guitar","guitar_residual")
    start=result["timeline"]["start_frame"]/44100;duration=result["timeline"]["num_frames"]/44100
    row={"id":"analysis_"+uuid4().hex,"name":("신스 패드" if family=="other" else "리드 기타")+f" 비교 · {start:g}–{start+duration:g}초", "state":"SUCCEEDED","stage":"실험 구간 분리 완료 · 청취 검증 필요","progress":100,"created":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"model":result["model_id"],"duration":duration,"kind":"prompt_detail","experiment_id":result["experiment_id"],"prompt":result["prompt"],"quality_improvement_verified":False,"job_ids":[],"original":str((out/"input.wav").relative_to(root)),"tracks":[{"family":label,"path":str((out/(role+".wav")).relative_to(root))} for label,role in zip(labels,("target","residual"))]}
    write_json(root/"web"/row["id"]/"record.json",row);return row


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-id",required=True);parser.add_argument("--prompt",required=True)
    parser.add_argument("--data-root",type=Path,default=project_root()/"data/separation")
    parser.add_argument("--repo",type=Path,default=project_root()/"data/separation/tools/AudioSep")
    parser.add_argument("--publish-library",action="store_true")
    args=parser.parse_args()
    import json
    result=run(args.data_root,args.experiment_id,args.prompt,args.repo)
    if args.publish_library:result["library"]=add_to_library(args.data_root,result)
    print(json.dumps(result,ensure_ascii=True,indent=2))
if __name__=="__main__":main()
