import numpy as np
import soundfile as sf
from pathlib import Path
from uuid import uuid4
from .common import project_root, read_json, write_json
from .ingest import ingest_file, load_asset
from .job_contracts import JobError, job_folder, verify_result
from .job_service import JobService

def run_pipeline(root, input_path=None, vocal_job_id=None, on_update=None):
    root=Path(root).resolve()
    policy=read_json(project_root()/"separation/configs/pipeline.json")
    service=JobService(root)
    if vocal_job_id is None:
        asset=ingest_file(Path(input_path),root)
        vocal=service.run(asset.name,"vocal_roformer",on_update)
    else:
        vocal=service.status(vocal_job_id)
    if vocal["state"]!="SUCCEEDED":
        raise JobError("VOCAL_STAGE_FAILED","Vocal stage did not succeed")
    if vocal["model_id"]!=policy["vocal_model"]:
        raise JobError("VOCAL_MODEL","Pipeline requires the selected RoFormer vocal model")
    vocal_folder=job_folder(root,vocal["job_id"])/"result"
    first=verify_result(vocal_folder,vocal)
    accompaniment=next(s for s in first["stems"] if s["family"]=="instrumental")
    derived=ingest_file(vocal_folder/accompaniment["path"],root)
    asset=load_asset(root,derived.name)
    with sf.SoundFile(vocal_folder/accompaniment["path"]) as original, sf.SoundFile(derived/"canonical.wav") as canonical:
        identical = original.frames == canonical.frames
        while identical and original.tell() < original.frames:
            identical = np.array_equal(original.read(441000,dtype="float32",always_2d=True), canonical.read(441000,dtype="float32",always_2d=True))
    if any(asset["timeline"][key]!=value for key,value in first["timeline"].items()) or not identical:
        raise JobError("INTERMEDIATE_CHANGED","Accompaniment ingestion changed raw audio or timeline")
    identifier="pipeline_"+uuid4().hex
    folder=root/"pipelines"/identifier
    folder.mkdir(parents=True)
    manifest={"kind":"separation_pipeline","schema_version":"1.0","pipeline_id":identifier,
              "state":"SEPARATING_INSTRUMENTS","original_asset_id":vocal["asset_id"],
              "original_source_sha256":first["source_sha256"],"timeline":first["timeline"],
              "vocal_job_id":vocal["job_id"],"instrumental_asset_id":derived.name,
              "instrumental_source_sha256":accompaniment["sha256"],
              "instrumental_canonical_sha256":asset["canonical"]["sha256"],
              "intermediate_samples_exact":True,
              "instrument_preset":policy["instrument_preset"],"stems":[],
              "mix_group":{"kind":"sequential_estimates","reconstruction_guaranteed":False},
              "quality":{"vocal_selection":"user_accepted","instrument_selection":"experimental",
                         "objective_accuracy":None}}
    write_json(folder/"manifest.json",manifest)
    try:
        second_job=service.run(derived.name,policy["instrument_preset"],on_update)
        manifest["instrument_job_id"]=second_job["job_id"]
        if second_job["state"]!="SUCCEEDED":
            raise JobError("INSTRUMENT_STAGE_FAILED","Instrument stage: "+second_job["state"])
        second_folder=job_folder(root,second_job["job_id"])/"result"
        second=verify_result(second_folder,second_job)
        for result_folder,stems in [(vocal_folder,[s for s in first["stems"] if s["family"]=="vocals"]),
                                    (second_folder,[s for s in second["stems"] if s["family"]!="vocals"])]:
            for stem in stems:
                manifest["stems"].append({**stem,"path":str((result_folder/stem["path"]).relative_to(root))})
        manifest["excluded_secondary_vocals"]=[s for s in second["stems"] if s["family"]=="vocals"]
        manifest["warnings"]=["Second-stage vocals are retained in its job for diagnosis but are not substituted for selected vocals.",
                              "Vocal removal may remove instrumental detail; downstream instrument quality is not yet accepted."]
        manifest["state"]="SUCCEEDED"
    except BaseException as error:
        manifest["state"]="FAILED"
        manifest["error"]={"code":getattr(error,"code","PIPELINE_ERROR"),"message":str(error)}
        write_json(folder/"manifest.json",manifest)
        raise
    write_json(folder/"manifest.json",manifest)
    return folder
