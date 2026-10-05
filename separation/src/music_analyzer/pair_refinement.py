from pathlib import Path
from uuid import uuid4
import html,json
import numpy as np
import soundfile as sf
from .audio import RATE,write_raw_streaming
from .common import read_json,write_json,sha256_file
from .ingest import ingest_file
from .job_contracts import job_folder,verify_result,JobError
from .job_service import JobService

def repartition(pair,estimated_guitar):
    if pair.shape!=estimated_guitar.shape or not np.isfinite(estimated_guitar).all():
        raise ValueError("Invalid pair estimate")
    return estimated_guitar.astype(np.float32), (pair-estimated_guitar).astype(np.float32)

def refine(root,job_id):
    root=Path(root).resolve()
    service=JobService(root)
    source_job=service.status(job_id)
    if source_job["state"]!="SUCCEEDED":
        raise JobError("SOURCE_STATE","Requires a successful instrument job")
    source_dir=job_folder(root,job_id)/"result"
    source=verify_result(source_dir,source_job)
    entries={s["family"]:s for s in source["stems"]}
    if not {"guitar","other"}<=entries.keys():
        raise JobError("SOURCE_STEMS","Requires guitar and other")
    folder=root/"refinements"/("refine_"+uuid4().hex)
    folder.mkdir(parents=True)
    manifest={"kind":"guitar_other_refinement","schema_version":"1.0","state":"PREPARING",
              "refinement_id":folder.name,"source_job_id":job_id,"source_sha256":source["source_sha256"],
              "timeline":source["timeline"],"method":"model_repartition_guitar_plus_other",
              "quality_improvement_verified":False,"stems":[]}
    write_json(folder/"manifest.json",manifest)
    try:
        guitar,_=sf.read(source_dir/entries["guitar"]["path"],dtype="float32",always_2d=True)
        other,_=sf.read(source_dir/entries["other"]["path"],dtype="float32",always_2d=True)
        pair=guitar+other
        write_raw_streaming(folder/"pair.wav",pair)
        asset=ingest_file(folder/"pair.wav",root)
        manifest["pair_asset_id"]=asset.name
        manifest["state"]="SEPARATING"
        write_json(folder/"manifest.json",manifest)
        job=service.run(asset.name,"instrument_roformer_6s")
        manifest["secondary_job_id"]=job["job_id"]
        if job["state"]!="SUCCEEDED":
            raise JobError("PAIR_STAGE_FAILED","Pair model: "+job["state"])
        result_dir=job_folder(root,job["job_id"])/"result"
        result=verify_result(result_dir,job)
        estimate_entry=next(s for s in result["stems"] if s["family"]=="guitar")
        estimate,_=sf.read(result_dir/estimate_entry["path"],dtype="float32",always_2d=True)
        new_guitar,new_other=repartition(pair,estimate)
        for family,audio in (("guitar",new_guitar),("other",new_other)):
            path=folder/"stems"/(family+".wav")
            properties=write_raw_streaming(path,audio)
            manifest["stems"].append({"family":family,"path":str(path.relative_to(root)),
                                     "sha256":sha256_file(path),**properties})
        for family,entry in entries.items():
            if family not in ("guitar","other"):
                manifest["stems"].append({**entry,"path":str((source_dir/entry["path"]).relative_to(root)),
                                          "unchanged_from_source":True})
        error=new_guitar.astype(np.float64)+new_other-pair
        manifest["pair_reconstruction_error_peak"]=float(np.abs(error).max())
        manifest["warnings"]=["Other is the pair minus new guitar; genuine other sounds may be reassigned incorrectly.",
                              "Same model on focused input is an experiment, not verified duplicate removal.",
                              "All non-pair outputs are unchanged; existing pair errors remain in its sum."]
        manifest["state"]="SUCCEEDED"
        write_json(folder/"manifest.json",manifest)
    except BaseException as error:
        manifest.update(state="FAILED",error={"message":str(error),"code":getattr(error,"code","REFINEMENT_ERROR")})
        write_json(folder/"manifest.json",manifest)
        raise
    return folder

def compare(root,folder,windows):
    root=Path(root).resolve()
    refined=read_json(folder/"manifest.json")
    if refined["state"]!="SUCCEEDED": raise ValueError("Refinement not successful")
    source_dir=job_folder(root,refined["source_job_id"])/"result"
    source=read_json(source_dir/"manifest.json")
    sources={"original":root/"inputs"/source["asset_id"]/"canonical.wav"}
    for stem in source["stems"]: sources["v0_"+stem["family"]]=source_dir/stem["path"]
    for stem in refined["stems"]: sources["v1_"+stem["family"]]=root/stem["path"]
    variants=[{"key":"v0","label":"기존 악기 분리","description":"사용자가 기타와 other의 겹침을 발견한 결과","stems":[s["family"] for s in source["stems"]]},
              {"key":"v1","label":"기타+other 재분리 후보","description":"두 트랙만 합쳐 모델에 다시 입력했습니다. 기타는 새 추정값, other는 합에서 기타를 뺀 잔차입니다. 나머지는 원래 결과 그대로입니다. 개선 여부는 청취 검증 대상입니다.","stems":[s["family"] for s in refined["stems"]]}]
    maximum=0.
    for path in sources.values():
        with sf.SoundFile(path) as audio:
            for block in audio.blocks(blocksize=RATE*10,dtype="float32",always_2d=True):
                maximum=max(maximum,float(np.abs(block).max()))
    gain=min(1.,.9/maximum) if maximum else 1.
    preview=folder/"comparison"
    preview.mkdir()
    (preview/"clips").mkdir()
    rendered=[]
    for i,(start,length) in enumerate(windows):
        if start<0 or length<=0 or length>60 or round((start+length)*RATE)>source["timeline"]["num_frames"]:
            raise ValueError("Invalid comparison window")
        files={}
        for key,path in sources.items():
            with sf.SoundFile(path) as audio:
                audio.seek(round(start*RATE))
                clip=audio.read(round(length*RATE),dtype="float32",always_2d=True)
            name=f"clips/w{i}_{key}.wav"
            sf.write(preview/name,clip*np.float32(gain),RATE,subtype="PCM_16")
            files[key]=name
        rendered.append({"start_sec":start,"duration_sec":length,"label":f"{start:g}–{start+length:g}초","files":files})
    data={"comparison_id":folder.name,"variants":variants,"windows":rendered,
          "preview":{"common_gain":gain,"dynamic_gain":False},"quality_improvement_verified":False}
    template=Path(__file__).with_name("comparison.html").read_text(encoding="utf-8")
    page=template.replace("__DATA__",json.dumps(data,ensure_ascii=False).replace("<","\\u003c"))
    page=page.replace("__SONG__",html.escape("기타 / other 재분리 비교")).replace("__GAIN__",f"{gain:.6f}")
    page=page.replace("원곡과","입력 반주와").replace("원곡에서","입력 반주에서").replace('vocals:"보컬"','vocals:"보컬 잔여물"')
    page=page.replace("각 작업의 result/stems 폴더","원래 작업의 result/stems 및 재분리 작업의 stems 폴더")
    (preview/"comparison.html").write_text(page,encoding="utf-8")
    write_json(preview/"manifest.json",data)
    return preview
