from __future__ import annotations
import math
import time
from pathlib import Path
import numpy as np
import soundfile as sf
import torch
import yaml
from .audio import RATE, write_raw_streaming
from .common import project_root, read_json, sha256_file, write_json

class ConfigLoader(yaml.SafeLoader):
    pass
ConfigLoader.add_constructor("tag:yaml.org,2002:python/tuple",
                            lambda loader,node: tuple(loader.construct_sequence(node)))

def load_config(registration):
    path=project_root()/"separation/configs/models"/registration.get("upstream_config_file","melband_roformer_kj.upstream.yaml")
    if sha256_file(path)!=registration["upstream_config_sha256"]:
        raise ValueError("ROFORMER_CONFIG_CHANGED")
    vendor=Path(__file__).parent/"vendor/msst"
    provenance=read_json(vendor/"PROVENANCE.json")
    if provenance["revision"]!=registration["code_revision"]:
        raise ValueError("ROFORMER_CODE_REVISION_CHANGED")
    for name in (("bs_roformer.py","attend.py","LICENSE") if registration.get("engine")=="bs_roformer" else ("mel_band_roformer.py","attend.py","LICENSE")):
        if sha256_file(vendor/name)!=provenance[name]["local_sha256"]:
            raise ValueError("ROFORMER_VENDOR_CHANGED")
    return yaml.load(path.read_text(),Loader=ConfigLoader)

def overlap_infer(audio, chunk, overlap, infer, check=lambda:None, tick=lambda:None, output_stems=None):
    """CPU accumulation with symmetric context padding and positive linear crossfades."""
    if audio.ndim!=2 or len(audio)!=2 or audio.shape[1]==0:
        raise ValueError("Expected nonempty stereo input")
    if chunk<2 or not 0<=overlap<1:
        raise ValueError("Invalid chunk parameters")
    stride=max(1,int(chunk*(1-overlap)))
    border=chunk-stride
    padded=np.pad(audio,((0,0),(border,border)),mode="reflect" if audio.shape[1]>1 else "edge")
    output_shape = (2,padded.shape[1]) if output_stems is None else (output_stems,2,padded.shape[1])
    result=np.zeros(output_shape,dtype=np.float32)
    weights=np.zeros(padded.shape[1],dtype=np.float32)
    fade=max(1,chunk//10)
    window=np.ones(chunk,dtype=np.float32)
    window[:fade]=np.linspace(1/fade,1,fade,dtype=np.float32)
    window[-fade:]=window[:fade][::-1]
    for offset in range(0,padded.shape[1],stride):
        check()
        length=min(chunk,padded.shape[1]-offset)
        piece=np.pad(padded[:,offset:offset+length],((0,0),(0,chunk-length)))
        prediction=np.asarray(infer(piece),dtype=np.float32)
        if prediction.shape!=((2,chunk) if output_stems is None else (output_stems,2,chunk)) or not np.isfinite(prediction).all():
            raise ValueError("Invalid RoFormer output")
        result[...,offset:offset+length]+=prediction[...,:length]*window[:length]
        weights[offset:offset+length]+=window[:length]
        tick()
    if not np.all(weights>0):
        raise ValueError("Uncovered output samples")
    result/=weights
    return result[...,border:border+audio.shape[1]].copy()

def run_roformer(request,root,attempt,asset,selected,checkpoint,registration,env,started,state,check,progress):
    multi = registration.get("engine")=="bs_roformer"
    if multi:
        from .vendor.msst.bs_roformer import BSRoformer as Model
    else:
        from .vendor.msst.mel_band_roformer import MelBandRoformer as Model
    configuration=load_config(registration)
    torch.manual_seed(selected["seed"])
    torch.cuda.manual_seed_all(selected["seed"])
    torch.backends.cuda.matmul.allow_tf32=False
    torch.backends.cudnn.allow_tf32=False
    loading=time.perf_counter()
    model=Model(**configuration["model"],**({} if multi else {"match_input_audio_length":True}))
    weights=torch.load(checkpoint,map_location="cpu",weights_only=True)
    if isinstance(weights,dict) and "state_dict" in weights:
        weights=weights["state_dict"]
    if all(key.startswith("module.") for key in weights):
        weights={key[7:]:value for key,value in weights.items()}
    if configuration["training"]["instruments"] != registration["source_labels"] and multi:
        raise ValueError("ROFORMER_SOURCE_ORDER_MISMATCH")
    model.load_state_dict(weights,strict=True)
    del weights
    model.eval().to("cuda")
    load_sec=time.perf_counter()-loading
    check()
    state("PREPROCESSING")
    audio,_=sf.read(root/"inputs"/request["asset_id"]/"canonical.wav",dtype="float32",always_2d=True)
    chunk=round(selected["segment_sec"]*RATE)
    stride=max(1,int(chunk*(1-selected["overlap"])))
    border=chunk-stride
    silent=not np.any(audio)
    progress["total"]=0 if silent else math.ceil((len(audio)+2*border)/stride)
    progress["completed"]=0
    torch.cuda.reset_peak_memory_stats()
    torch.cuda.synchronize()
    inference_started=time.perf_counter()
    state("SEPARATING")
    def infer(piece):
        with torch.inference_mode(),torch.autocast("cuda",dtype=torch.float16):
            output=model(torch.from_numpy(piece).unsqueeze(0).to("cuda"))
        return output[0].float().cpu().numpy()
    def tick():
        progress["completed"]+=1
        state("SEPARATING")
        check()
    count=len(registration["source_labels"]) if multi else None
    estimate=np.zeros((count,2,len(audio)) if multi else (2,len(audio)),dtype=np.float32) if silent else overlap_infer(audio.T,chunk,selected["overlap"],infer,check,tick,output_stems=count)
    torch.cuda.synchronize()
    inference_sec=time.perf_counter()-inference_started
    memory={"peak_allocated_bytes":torch.cuda.max_memory_allocated(),"peak_reserved_bytes":torch.cuda.max_memory_reserved(),"measurement":"PyTorch allocator; not whole-device peak"}
    prediction=estimate if multi else np.stack([estimate,audio.T-estimate])
    state("VALIDATING_OUTPUT")
    target=attempt/"result.partial"
    target.mkdir()
    stems=[]
    state("EXPORTING")
    for label,estimate in zip(registration["source_labels"],prediction,strict=True):
        check()
        path=target/"stems"/(label+".wav")
        properties=write_raw_streaming(path,estimate.T,check)
        stems.append({"id":"stem_"+label,"family":label,"canonical_id":registration["source_mapping"][label],
                      "path":"stems/"+label+".wav","sha256":sha256_file(path),"presence":"unknown",
                      "quality_score":None,"derivation":"model_estimate" if multi or label=="vocals" else "input_minus_estimated_vocals",**properties})
    error=prediction.astype(np.float64).sum(axis=0).T-audio
    manifest={"kind":"separation_result","schema_version":"1.0","status":"succeeded",
              "job_id":request["job_id"],"asset_id":request["asset_id"],
              "source_sha256":asset["canonical"]["sha256"],"original_sha256":asset["input"]["sha256"],
              "timeline":{"sample_rate":RATE,"channels":2,"num_frames":len(audio),"origin_sec":0},
              "model":registration,"preset":selected,"requested_preset":request["requested_preset"],
              "actual_preset":request["preset_name"],"attempt_id":attempt.name,"inference_performed":not silent,
              "environment_lock_sha256":env["environment_lock_sha256"],
              "pipeline_code_sha256":{name:sha256_file(Path(__file__).parent/name) for name in ("roformer_runner.py","worker.py","registry.py","audio.py","job_service.py","job_contracts.py")},
              "normalization":{"scope":"none","per_stem_gain":1.0},
              "stems":stems,"warnings":["No reference stems: perceptual quality is not scored",
                                        "Instrument candidate has unverified training provenance" if multi else "Accompaniment is a residual; reconstruction does not measure separation quality"],
              "mix_group":{"kind":"estimated_partition" if multi else "model_vocals_plus_input_residual","reconstruction_guaranteed":not multi,"tolerance":"float32_roundoff"},
              "timing":{"model_load_sec":load_sec,"inference_sec":inference_sec,"rtf":inference_sec/(len(audio)/RATE),"wall_sec":time.perf_counter()-started},
              "memory":memory,"diagnostics":{"reconstruction_error_rms":float(np.sqrt(np.mean(error**2))),
                    "reconstruction_error_peak":float(np.abs(error).max()),"reference_available":False,
                    "raw_sdr":None,"si_sdr":None,"quality_assessment":"not_performed"}}
    check()
    write_json(target/"manifest.json",manifest)
    state("READY_TO_PUBLISH")
    return 0
