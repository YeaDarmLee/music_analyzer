"""Pinned CLAPSep short-clip experiment; run in clapsep-env."""
import argparse,os,sys,time,contextlib,io
from pathlib import Path
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
from filelock import FileLock
from .common import project_root,read_json,write_json,sha256_file
from .audio import write_raw
from .audiosep_experiment import restore_channel,add_to_library
from .substem_experiment import folder,publish
from .roformer_runner import overlap_infer


def run(root,identifier,positive,negative):
    if not positive.strip() or max(len(positive),len(negative))>300:raise ValueError("Invalid query")
    root=Path(root).resolve();out=folder(root,identifier);manifest=read_json(out/"manifest.json")
    if manifest["state"]!="PREPARED" or manifest["parent_family"] not in ("other","guitar"):raise ValueError("Fresh other experiment required")
    repo=root/"tools/CLAPSepInference";registration=read_json(project_root()/"separation/configs/models/clapsep.json")
    for name,digest in registration["code_hashes"].items():
        if sha256_file(repo/name)!=digest:raise ValueError("CLAPSep code changed")
    for artifact in registration["artifacts"]:
        if sha256_file(repo/"model"/artifact["filename"])!=artifact["sha256"]:raise ValueError("CLAPSep weight changed")
    if sha256_file(out/"input.wav")!=manifest["input_sha256"]:raise ValueError("Input changed")
    audio,rate=sf.read(out/"input.wav",dtype="float32",always_2d=True)
    if rate!=44100 or audio.shape!=(manifest["timeline"]["num_frames"],2):raise ValueError("Invalid input timeline")
    config={"lan_embed_dim":1024,"depths":[1,1,1,1],"embed_dim":128,"encoder_embed_dim":128,"phase":False,"spec_factor":8,"d_attn":640,"n_masker_layer":3,"conv":False}
    started=time.perf_counter();runtime=root/"runtime";runtime.mkdir(exist_ok=True)
    os.environ["WANDB_DISABLED"]="true"
    with FileLock(str(runtime/"supervisor.lock"),timeout=0),FileLock(str(runtime/"gpu-execution.lock"),timeout=0):
        sys.path.insert(0,str(repo))
        import torch
        from model.CLAPSep import CLAPSep
        if not torch.cuda.is_available():raise ValueError("CUDA required")
        torch.manual_seed(0);torch.cuda.reset_peak_memory_stats()
        with contextlib.redirect_stdout(io.StringIO()):
            model=CLAPSep(config,str(repo/"model/music_audioset_epoch_15_esc_90.14.pt"))
        checkpoint=torch.load(repo/"model/best_model.ckpt",map_location="cpu",weights_only=True)
        incompatible=model.load_state_dict(checkpoint,strict=False)
        required={key for key,parameter in model.named_parameters() if parameter.requires_grad}
        missing=required.intersection(incompatible.missing_keys)
        if incompatible.unexpected_keys or missing:raise ValueError("CLAPSep trainable checkpoint mismatch: "+str(sorted(missing)[:8]))
        model.eval().to("cuda");model.clap_model.device=torch.device("cuda")
        with torch.inference_mode():
            embed_pos,embed_neg=torch.chunk(model.clap_model.get_text_embedding([positive,negative],use_tensor=True),2,dim=0)
            if not negative:embed_neg=torch.zeros_like(embed_neg)
            native=resample_poly(audio.T,320,441,axis=1).astype(np.float32)
            progress=0
            def infer(piece):
                channels=[]
                for channel in piece:
                    output=model.inference_from_data(torch.from_numpy(channel)[None,:].to("cuda"),embed_pos,embed_neg)
                    channels.append(output[0].float().cpu().numpy())
                return np.stack(channels)
            def tick():
                nonlocal progress
                progress+=1;print("completed chunk",progress,flush=True)
            target=overlap_infer(native,320000,.5,infer,tick=tick)
            restored=np.column_stack([restore_channel(channel,len(audio)) for channel in target])
        torch.cuda.synchronize();memory=torch.cuda.max_memory_allocated()
    estimate=out/"clapsep-estimate.wav";write_raw(estimate,restored)
    result=publish(root,identifier,estimate,"clapsep",positive)
    result.update(model_inference_performed=True,estimate_origin="clapsep_independent_channel_inference",negative_prompt=negative,model=registration,wall_sec=time.perf_counter()-started,peak_allocated_bytes=memory,chunk_sec=10,overlap=.5,quality_improvement_verified=False)
    write_json(out/"manifest.json",result);return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--experiment-id",required=True)
    parser.add_argument("--positive",default="A sustained synthesizer pad playing in the background")
    parser.add_argument("--negative",default="Electric guitar, piano, drums and singing")
    parser.add_argument("--name",default="")
    parser.add_argument("--no-library",action="store_true")
    parser.add_argument("--data-root",type=Path,default=project_root()/"data/separation")
    args=parser.parse_args();result=run(args.data_root,args.experiment_id,args.positive,args.negative)
    if args.no_library:return
    row=add_to_library(args.data_root,result);row["name"]=(args.name+" · " if args.name else "")+"CLAPSep · "+row["name"]
    write_json(args.data_root/"web"/row["id"]/"record.json",row)
    print("READY",row["id"],row["name"],flush=True)
if __name__=="__main__":main()
