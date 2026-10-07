"""Loopback-only web API and built Vue frontend. No external audio uploads."""
from __future__ import annotations
import argparse,hashlib,io,json,mimetypes,re,shutil,threading,time,urllib.parse,zipfile
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from http.cookies import SimpleCookie, CookieError
from .auth import AuthStore, AuthError, DatabaseUnavailable, COOKIE_NAME, SESSION_SECONDS
from pathlib import Path
from uuid import uuid4
import numpy as np
import soundfile as sf
from .common import project_root,read_json,write_json,sha256_file
from .ingest import ingest_file,load_asset
from .job_service import JobService
from .job_contracts import job_folder,verify_result,JobError
from .audio import RATE
from . import release
from .legal import RIGHTS_CONFIRMATION_VERSION,public_versions,require_consents,ConsentError

BUSY_STATES=("QUEUED","RUNNING")
STORED_ID=re.compile(r"(?:job|asset)_[0-9a-f]{32}")
stored_ids=lambda text:set(STORED_ID.findall(text))

class WebLibrary:
    def __init__(self,root):
        self.root=Path(root).resolve()
        self.web=self.root/"web"
        self.web.mkdir(parents=True,exist_ok=True)
        self.executor=ThreadPoolExecutor(max_workers=1)
        self.cache_lock=threading.Lock()
        self.gain_cache={}
        self.stopping=threading.Event()
        for path in self.web.glob("analysis_*/record.json"):
            record=read_json(path)
            if record["state"] not in ("SUCCEEDED","FAILED","CANCELLED"):
                record.update(state="FAILED",stage="실행 중 서버가 종료됐습니다. 새 분석으로 다시 실행해 주세요.",error="서버 종료로 분석이 중단됐습니다.")
                write_json(path,record)

    def safe(self,path):
        value=(self.root/path).resolve()
        if not value.is_relative_to(self.root) or not value.is_file(): raise FileNotFoundError("파일을 찾을 수 없습니다.")
        return value

    def entries(self,identifiers=None):
        if identifiers is not None:
            rows=[]
            for identifier in identifiers:
                try:rows.append(self.get(identifier))
                except FileNotFoundError:pass
            return sorted(rows,key=lambda r:str(r["created"]),reverse=True)
        rows={}
        vocal_names={}
        vocal_records={}
        consumed_vocals=set()
        for path in (self.root/"jobs").glob("*/result/manifest.json"):
            try:
                m=read_json(path)
                a=read_json(self.root/"inputs"/m["asset_id"]/"manifest.json")
                if m.get("model",{}).get("model_id")!="melband_roformer_kj":continue
                vocal=next(s for s in m["stems"] if s["family"]=="vocals")
                record={"name":a["input"]["original_name"],"timeline":m["timeline"],
                        "job_id":m["job_id"],"original":str((self.root/"inputs"/m["asset_id"]/"canonical.wav").relative_to(self.root)),
                        "track":{**vocal,"path":str((path.parent/vocal["path"]).relative_to(self.root))}}
                vocal_records[m["source_sha256"]]=record
                for stem in m["stems"]:
                    if stem["family"]=="instrumental":
                        vocal_names[stem["sha256"]]=a["input"]["original_name"]
                        vocal_records[stem["sha256"]]=record
            except (OSError,ValueError,KeyError): pass
        for path in (self.root/"jobs").glob("*/job.json"):
            try:
                job=read_json(path)
                if job["state"]!="SUCCEEDED": continue
                if job.get("model_id") in ("melband_karaoke","bs_karaoke"):continue
                folder=path.parent/"result"
                m=read_json(folder/"manifest.json")
                a=read_json(self.root/"inputs"/m["asset_id"]/"manifest.json")
                name=a["input"]["original_name"]
                if name=="pair.wav": continue
                if name=="instrumental.wav": name=vocal_names.get(a["input"]["sha256"],"보컬 제거 반주")
                rows[job["job_id"]]={"id":job["job_id"],"name":Path(name).stem,"state":"SUCCEEDED",
                    "stage":"분석 완료","progress":100,"created":job["created_at_utc"],
                    "duration":m["timeline"]["num_frames"]/RATE,"model":job["requested_preset"],
                    "tracks":[{**s,"path":str((folder/s["path"]).relative_to(self.root))} for s in m["stems"]],
                    "original":str((self.root/"inputs"/m["asset_id"]/"canonical.wav").relative_to(self.root)),
                    "asset_id":m["asset_id"]}
                if "instrumental" not in {t["family"] for t in m["stems"]}:
                    parent=vocal_records.get(a["input"]["sha256"]) or vocal_records.get(m["source_sha256"])
                    row=rows[job["job_id"]]
                    if parent and parent["timeline"]==m["timeline"]:
                        row["tracks"]=[parent["track"]]+[t for t in row["tracks"] if t["family"]!="vocals"]
                        row.update(name=Path(parent["name"]).stem,original=parent["original"],
                                   vocal_source="roformer",vocal_job_id=parent["job_id"],
                                   secondary_vocals_excluded=True)
                        consumed_vocals.add(parent["job_id"])
                    elif a["input"]["original_name"]=="instrumental.wav":
                        row["tracks"]=[t for t in row["tracks"] if t["family"]!="vocals"]
                        row.update(secondary_vocals_excluded=True,vocal_source="unavailable")

            except (OSError,KeyError,ValueError): pass
        for identifier in consumed_vocals:rows.pop(identifier,None)
        for path in (self.root/"pipelines").glob("*/manifest.json"):
            try:
                m=read_json(path)
                if m["state"]!="SUCCEEDED": continue
                a=read_json(self.root/"inputs"/m["original_asset_id"]/"manifest.json")
                rows[m["pipeline_id"]]={"id":m["pipeline_id"],"name":Path(a["input"]["original_name"]).stem,
                    "state":"SUCCEEDED","stage":"분석 완료","progress":100,"created":path.stat().st_mtime,
                    "duration":m["timeline"]["num_frames"]/RATE,"model":m["instrument_preset"],
                    "tracks":m["stems"],"vocal_source":"roformer","secondary_vocals_excluded":True,"original":str((self.root/"inputs"/m["original_asset_id"]/"canonical.wav").relative_to(self.root))}
            except (OSError,KeyError,ValueError): pass
        for path in self.web.glob("analysis_*/record.json"):
            try:
                r=read_json(path)
                rows[r["id"]]=r
                for job_id in r.get("job_ids",[]): rows.pop(job_id,None)
            except (OSError,ValueError): pass
        return sorted(rows.values(),key=lambda r:str(r["created"]),reverse=True)

    def get(self,identifier):
        if not re.fullmatch(r"(job|pipeline|analysis)_[0-9a-f]{32}",identifier): raise ValueError("잘못된 분석 ID입니다.")
        if identifier.startswith("analysis_"):
            row=read_json(self.web/identifier/"record.json")
            if row.get("id")!=identifier:raise FileNotFoundError("분석을 찾을 수 없습니다.")
            if row.get("state")=="SUCCEEDED" and row.get("groups"):
                row=self.flatten_session(row)
                write_json(self.web/identifier/"record.json",row)
            return row
        for row in self.entries():
            if row["id"]==identifier:return row
        raise FileNotFoundError("분석을 찾을 수 없습니다.")

    def public(self,row):
        return {k:v for k,v in row.items() if k not in ("tracks","original","instrumental","job_ids","input_path")}|{"track_count":sum(not self.output_silent(t) for t in row.get("tracks",[]))}

    def create(self,filename,preset,stream,length,claim=None,rights=None):
        if preset not in ("basic_2","basic_6","final_11","final_10","commercial_13","instrument_roformer_6s","quality_6s"): raise ValueError("지원하지 않는 모델입니다.")
        release.require_allowed(preset,self.root)  # commercial profile: allowlist + approval gate, fail closed
        extension=Path(filename).suffix.lower()
        if extension not in (".mp3",".wav",".flac"): raise ValueError("MP3, WAV, FLAC 파일을 선택해 주세요.")
        if not 0<length<=1024**3:raise ValueError("파일은 1GB 이하여야 합니다.")
        if rights!=RIGHTS_CONFIRMATION_VERSION:raise ValueError("업로드한 음원의 이용 권한을 확인해 주세요.")
        if shutil.disk_usage(self.web).free<length+3*1024**3:raise ValueError("분석을 위한 디스크 공간이 부족합니다.")
        identifier="analysis_"+uuid4().hex
        folder=self.web/identifier
        folder.mkdir()
        upload=folder/("source"+extension)
        try:
            with upload.open("wb") as output:
                remaining=length
                while remaining:
                    block=stream.read(min(1024**2,remaining))
                    if not block:raise ValueError("파일 업로드가 중단됐습니다.")
                    output.write(block);remaining-=len(block)
        except BaseException:
            upload.unlink(missing_ok=True)
            raise
        row={"id":identifier,"name":Path(filename).stem[:160],"filename":filename[:200],"state":"QUEUED",
             "stage":"분석 대기 중","progress":0,"created":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
             "model":preset,"duration":0,"tracks":[],"job_ids":[],"vocal_source":"roformer","secondary_vocals_excluded":True,
             "rights_confirmation_version":rights,"rights_confirmed_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())}
        write_json(folder/"record.json",row)
        if claim:claim(identifier)
        self.executor.submit(self.analyze,folder,upload,row)
        return self.public(row)

    def create_vocal_detail(self,identifier,preset="bs_karaoke",claim=None,visible=None):
        release.require_development("vocal_detail")
        if preset not in ("bs_karaoke","karaoke_roformer"):raise ValueError("지원하지 않는 보컬 분리 모델입니다.")
        parent=self.get(identifier)
        if parent["state"]!="SUCCEEDED" or not any(t["family"]=="vocals" for t in parent["tracks"]):raise ValueError("완료한 보컬 트랙이 필요합니다.")
        from .registry import resolve
        resolve(self.root,"bs_karaoke" if preset=="bs_karaoke" else "melband_karaoke")
        if shutil.disk_usage(self.web).free<3*1024**3:raise ValueError("분석 공간이 부족합니다.")
        for existing in self.entries():
            if visible and not visible(existing["id"]):continue
            if existing.get("parent_analysis_id")==identifier and existing.get("model")==preset and existing["state"] in ("QUEUED","RUNNING"):return self.public(existing)
        row={"id":"analysis_"+uuid4().hex,"name":parent["name"]+" · 리드/코러스", "state":"QUEUED","stage":"보컬 세부분리 대기 중","progress":0,
             "created":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"model":preset,"duration":parent["duration"],
             "tracks":[],"job_ids":[],"parent_analysis_id":identifier,"kind":"vocal_detail","quality_improvement_verified":False,
             "rights_confirmation_version":parent.get("rights_confirmation_version"),"rights_confirmed_at":parent.get("rights_confirmed_at")}
        folder=self.web/row["id"];write_json(folder/"record.json",row)
        if claim:claim(row["id"])
        self.executor.submit(self.analyze_vocal_detail,folder,self.track_path(parent,"vocals"),row)
        return self.public(row)

    def analyze_vocal_detail(self,folder,source,row):
        def save(**values):row.update(values);write_json(folder/"record.json",row)
        try:
            save(state="RUNNING",stage="보컬 입력 준비",progress=2)
            asset=ingest_file(source,self.root)
            def update(job):
                p=job.get("progress") or {};fraction=p.get("completed",0)/max(1,p.get("total",0))
                save(state="RUNNING",stage="리드/코러스 분리 중",progress=min(97,5+round(90*fraction)),active_job_id=job["job_id"],completed_chunks=p.get("completed",0),total_chunks=p.get("total",0))
            service=JobService(self.root)
            while not self.stopping.is_set():
                try:job=service.run(asset.name,row["model"],update);break
                except JobError as error:
                    if error.code!="GPU_BUSY":raise
                    save(state="QUEUED",stage="다른 분석이 끝나기를 기다리는 중");self.stopping.wait(1)
            else:raise ValueError("서버가 종료되었습니다.")
            if job["state"]!="SUCCEEDED":raise ValueError(str(job.get("error") or job["state"]))
            result_folder=job_folder(self.root,job["job_id"])/"result";result=verify_result(result_folder,job)
            tracks=[{**t,"path":str((result_folder/t["path"]).relative_to(self.root))} for t in result["stems"]]
            save(state="SUCCEEDED",stage="보컬 세부분리 완료 · 품질 청취 확인 필요",progress=100,tracks=tracks,job_ids=[job["job_id"]],active_job_id=None,original=str((asset/"canonical.wav").relative_to(self.root)))
        except Exception as error:save(state="FAILED",stage="보컬 세부분리 실패",error=str(error),active_job_id=None)

    def analyze(self,folder,upload,row):
        started=time.monotonic()
        waiting_seconds=0.
        service=JobService(self.root)
        commercial=row["model"]=="commercial_13"
        is11=row["model"] in ("final_11","commercial_13")
        if commercial:
            from .commercial_pipeline import STAGE_PRESETS,MODELS as COMMERCIAL_MODELS
            from .registry import commercial_gate
        else:STAGE_PRESETS={}
        def save(**values):
            if values.get("state")=="SUCCEEDED":
                values.update(processing_seconds=round(time.monotonic()-started-waiting_seconds,3),timing_profile="staged-v8-overlap40")
            row.update(values);write_json(folder/"record.json",row)
        def update(job,base,span,stage):
            p=job.get("progress") or {}
            fraction=p.get("completed",0)/max(1,p.get("total",0)) if p.get("total") else 0
            percent=max(row["progress"],min(99,base+span*fraction))
            save(state="RUNNING",stage=stage,progress=round(percent,1),active_job_id=job["job_id"],
                 completed_chunks=p.get("completed",0),total_chunks=p.get("total",0))
        def run_stage(asset_id,preset_name,callback):
            nonlocal waiting_seconds
            preset_name=STAGE_PRESETS.get(preset_name,preset_name)
            release.require_stage(preset_name)
            while not self.stopping.is_set():
                try:return service.run(asset_id,preset_name,callback)
                except JobError as error:
                    if error.code!="GPU_BUSY":raise
                    save(state="QUEUED",stage="다른 음원 처리 완료를 기다리는 중")
                    wait_started=time.monotonic()
                    self.stopping.wait(1)
                    waiting_seconds+=time.monotonic()-wait_started
            raise ValueError("서버 종료로 분석이 중단됐습니다.")
        try:
            if commercial:commercial_gate(COMMERCIAL_MODELS,self.root)
            save(state="RUNNING",stage="음원 확인 및 변환",progress=2)
            asset=ingest_file(upload,self.root)
            upload.unlink(missing_ok=True)  # the validated asset keeps the only retained copy of the upload
            original=load_asset(self.root,asset.name)
            save(duration=original["timeline"]["num_frames"]/RATE,progress=5)
            vocal=run_stage(asset.name,"vocal_roformer",lambda j:update(j,5,27,"보컬·반주 분리 중"))
            row["job_ids"].append(vocal["job_id"])
            if vocal["state"]!="SUCCEEDED":raise ValueError("보컬 분리를 완료하지 못했습니다: "+vocal["state"])
            first_dir=job_folder(self.root,vocal["job_id"])/"result"
            first=verify_result(first_dir,vocal)
            instrumental=next(s for s in first["stems"] if s["family"]=="instrumental")
            original_path=str((asset/"canonical.wav").relative_to(self.root))
            instrumental_path=str((first_dir/instrumental["path"]).relative_to(self.root))
            if row["model"]=="basic_2":
                save(stage="길이·합계 검증 및 저장",progress=97)
                row.update(original=original_path,tracks=[{**s,"path":str((first_dir/s["path"]).relative_to(self.root))} for s in first["stems"] if s["family"] in ("vocals","instrumental")],track_layout="basic_2")
                self.validate_partition(row["original"],row["tracks"])
                save(state="SUCCEEDED",stage="분석 완료",progress=100,tracks=[self.track_activity(t) for t in row["tracks"]],active_job_id=None)
                return
            if is11:
                context_job=run_stage(asset.name,"instrument_mega7",lambda j:update(j,32,8,"원곡 악기 근거 확인 중"))
                row["job_ids"].append(context_job["job_id"])
                if context_job["state"]!="SUCCEEDED":raise ValueError("원곡 악기 근거 추출 실패")
                context_dir=job_folder(self.root,context_job["job_id"])/"result"
                context=verify_result(context_dir,context_job)
                from .instrumental_restoration import apply as restore_instrumental
                row,first=restore_instrumental(self.root,row,first_dir,first,context_dir,context)
                instrumental=next(s for s in first["stems"] if s["family"]=="instrumental")
                instrumental_path=str((first_dir/instrumental["path"]).relative_to(self.root))
                save(stage="리드 보컬·코러스 준비",progress=40,completed_chunks=0,total_chunks=0)
                vocal_stem=next(t for t in first["stems"] if t["family"]=="vocals")
                vocal_asset=ingest_file(first_dir/vocal_stem["path"],self.root)
                detail_job=run_stage(vocal_asset.name,"bs_karaoke",lambda j:update(j,40,10,"리드 보컬·코러스 분리 중"))
                row["job_ids"].append(detail_job["job_id"])
                if detail_job["state"]!="SUCCEEDED":raise ValueError("리드·코러스 분리 실패")
                detail_dir=job_folder(self.root,detail_job["job_id"])/"result"
                detail_result=verify_result(detail_dir,detail_job)
            save(stage="악기 분리 준비",progress=50 if is11 else 32,completed_chunks=0,total_chunks=0)
            second_asset=ingest_file(first_dir/instrumental["path"],self.root)
            final=row["model"] in ("final_10","final_11","commercial_13")
            basic=row["model"]=="basic_6"
            second=run_stage(second_asset.name,"instrument_roformer_6s" if final or basic else row["model"],lambda j:update(j,50 if is11 else 32,52 if basic else 20,"피아노·기타·베이스·드럼 분리 중" if basic else "피아노·베이스·드럼 분리 중" if final else "악기 분리 중"))
            row["job_ids"].append(second["job_id"])
            if second["state"]!="SUCCEEDED":raise ValueError("악기 분리를 완료하지 못했습니다: "+second["state"])
            second_dir=job_folder(self.root,second["job_id"])/"result"
            second_result=verify_result(second_dir,second)
            if basic:
                save(stage="반주 구성 정리",progress=84)
                instruments=[{**s,"path":str((second_dir/s["path"]).relative_to(self.root)),**({"display_name":"기타"} if s["family"]=="guitar" else {})} for s in second_result["stems"] if s["family"] in ("piano","guitar","bass","drums")]
                if {t["family"] for t in instruments}!={"piano","guitar","bass","drums"}:raise ValueError("6트랙 악기 출력이 누락됐습니다.")
                instruments.sort(key=lambda t:("piano","guitar","bass","drums").index(t["family"]))
                vocals=[{**s,"path":str((first_dir/s["path"]).relative_to(self.root))} for s in first["stems"] if s["family"]=="vocals"]
                row.update(original=original_path,instrumental=instrumental_path)
                row=self.with_remaining(row,vocals+instruments,"basic_6","remaining-basic6.wav",instrumental_path,instruments)
                save(stage="길이·합계 검증 및 저장",progress=97)
                self.validate_partition(instrumental_path,[t for t in row["tracks"] if t["family"]!="vocals"])
                save(state="SUCCEEDED",stage="분석 완료",progress=100,tracks=[self.track_activity(t) for t in row["tracks"]],active_job_id=None)
                return
            tracks=[]
            for base,stems in [(first_dir,[s for s in first["stems"] if s["family"]=="vocals"]),
                               (second_dir,[s for s in second_result["stems"] if s["family"] in ("piano","bass","drums") or not final and s["family"]!="vocals"])]:
                tracks.extend({**s,"path":str((base/s["path"]).relative_to(self.root))} for s in stems)
            if is11:
                base_tracks=[{**t,"path":str((second_dir/t["path"]).relative_to(self.root))} for t in second_result["stems"] if t["family"] in ("piano","guitar","bass","drums")]
                if {t["family"] for t in base_tracks}!={"piano","guitar","bass","drums"}:raise ValueError("기본 악기 출력 누락")
                row.update(original=original_path,instrumental=instrumental_path)
                save(stage="추가 악기 분리 준비",progress=70)
                residual1=self.with_remaining(row,[],"staged_v1","remaining-stage1.wav",instrumental_path,base_tracks)["tracks"][-1]
                guitar=next(t for t in base_tracks if t["family"]=="guitar")
                guitar_asset=ingest_file(self.root/guitar["path"],self.root)
                guitar_job=run_stage(guitar_asset.name,"instrument_mega5",lambda j:update(j,70,7,"어쿠스틱·일렉기타 분리 중"))
                row["job_ids"].append(guitar_job["job_id"])
                if guitar_job["state"]!="SUCCEEDED":raise ValueError("기타 재분리 실패")
                guitar_dir=job_folder(self.root,guitar_job["job_id"])/"result"
                guitar_result=verify_result(guitar_dir,guitar_job)
                guitars=[{**t,"path":str((guitar_dir/t["path"]).relative_to(self.root))} for t in guitar_result["stems"] if t["family"] in ("acoustic-guitar","electric-guitar")]
                if {t["family"] for t in guitars}!={"acoustic-guitar","electric-guitar"}:raise ValueError("기타 재분리 출력 누락")
                guitar_residual=self.with_remaining(row,[],"staged_v1","guitar-residual.wav",guitar["path"],guitars)["tracks"][-1]
                guitar_residual.update(family="guitar_residual",display_name="기타 보조")
                residual_asset=ingest_file(self.root/residual1["path"],self.root)
                instrument_job=run_stage(residual_asset.name,"instrument_mega5",lambda j:update(j,77,7,"신디·스트링·브라스 분리 중"))
                row["job_ids"].append(instrument_job["job_id"])
                row["tonal_job_id"]=instrument_job["job_id"]
                if instrument_job["state"]!="SUCCEEDED":raise ValueError("나머지 악기 추출 실패")
                instrument_dir=job_folder(self.root,instrument_job["job_id"])/"result"
                result=verify_result(instrument_dir,instrument_job)
                tracks.extend(guitars)
                tracks.extend({**t,"path":str((instrument_dir/t["path"]).relative_to(self.root))} for t in result["stems"] if t["family"] in ("synth","bowed_strings","brass"))
            elif final:
                instruments=run_stage(second_asset.name,"instrument_mega5",lambda j:update(j,70 if is11 else 52,14,"신디사이저·스트링·브라스·기타 분리 중"))
                row["job_ids"].append(instruments["job_id"])
                if instruments["state"]!="SUCCEEDED":raise ValueError("전용 악기 분리를 완료하지 못했습니다.")
                instrument_dir=job_folder(self.root,instruments["job_id"])/"result"
                result=verify_result(instrument_dir,instruments)
                tracks.extend({**s,"path":str((instrument_dir/s["path"]).relative_to(self.root))} for s in result["stems"])
            if not is11:
                save(stage="리드 보컬·코러스 준비",progress=66 if final else 51,completed_chunks=0,total_chunks=0)
                vocal_track=next(t for t in tracks if t["family"]=="vocals")
                vocal_asset=ingest_file(self.root/vocal_track["path"],self.root)
                detail_job=run_stage(vocal_asset.name,"bs_karaoke",lambda j:update(j,66 if final else 52,18 if final else 14,"리드 보컬·코러스 분리 중"))
                row["job_ids"].append(detail_job["job_id"])
                if detail_job["state"]!="SUCCEEDED":raise ValueError("리드·코러스 분리 실패")
                detail_dir=job_folder(self.root,detail_job["job_id"])/"result"
                detail_result=verify_result(detail_dir,detail_job)
            if commercial:
                from .vocal_split import publish as publish_vocal_split
                detail_stems=publish_vocal_split(self.root,folder,first_dir/vocal_stem["path"],detail_dir,detail_result)
            else:detail_stems=[{**t,"path":str((detail_dir/t["path"]).relative_to(self.root))} for t in detail_result["stems"]]
            tracks.extend({**t,"parent_family":"vocals"} for t in detail_stems)
            row["tracks"]=tracks
            row["original"]=str((asset/"canonical.wav").relative_to(self.root))
            if final:
                row["instrumental"]=str((first_dir/instrumental["path"]).relative_to(self.root))
                row["separation_version"]=("commercial-13-v1" if commercial else "staged-context-pads-v16") if is11 else "instrumental-with-brass-v5"
                if is11:row["recovery_policy"]="base-estimates-only-v1"
            if final:save(stage="반주 구성 정리" if is11 else "반주 구성 정리 중",progress=84,completed_chunks=0,total_chunks=0)
            if is11:
                row["tracks"].append(guitar_residual)
            row=self.final_session(row) if final else self.flatten_session(row)
            if is11:
                save(stage="피아노 내 심벌 혼입 보완 중",progress=85,completed_chunks=0,total_chunks=0)
                def cymbal_progress(p):
                    save(progress=round(85+10*p["completed"]/max(1,p["total"]),1),completed_chunks=p["completed"],total_chunks=p["total"])
                if commercial:
                    from .commercial_cymbal import apply as commercial_cymbal
                    row=commercial_cymbal(self.root,row)
                else:
                    from .synth_recovery import run_for_library  # CLAPSep path: development-only, never imported for commercial_13
                    row=run_for_library(self,row,'cymbal',on_progress=cymbal_progress)
                from .percussion_refinement import apply as route_percussion,prepare_source
                context_sources={s['family']:context_dir/s['path'] for s in context['stems']}
                percussion_asset=ingest_file(prepare_source(self.root,row),self.root)
                percussion_job=run_stage(percussion_asset.name,"instrument_mega7",lambda j:update(j,95,1,"종소리·팀파니 근거 확인 중"))
                row['job_ids'].append(percussion_job['job_id'])
                if percussion_job['state']!='SUCCEEDED':raise ValueError('추가 타악기 근거 추출 실패')
                percussion_dir=job_folder(self.root,percussion_job['job_id'])/'result'
                percussion_result=verify_result(percussion_dir,percussion_job)
                percussion_sources={s['family']:percussion_dir/s['path'] for s in percussion_result['stems']}
                row['percussion_context_job_id']=percussion_job['job_id']
                save(stage="종소리·팀파니·기타 타악기 분류 중",progress=96)
                row=route_percussion(self.root,row,context_sources['percussion'],context_job['job_id'],
                                     additional=(context_sources['timpani'],percussion_sources['percussion'],percussion_sources['timpani']),
                                     version='context-supported-percussion-v2')
                from .string_routing import apply as route_strings
                save(stage="흩어진 스트링 성분 정리 중",progress=96.5)
                row=route_strings(self.root,row,{f:context_sources[f] for f in ('synth','bowed_strings','brass')},context_job['job_id'])
                from .percussion_refinement import apply_backing,RIVALS
                row=apply_backing(self.root,row,{f:context_sources[f] for f in ('percussion','timpani',*RIVALS)},context_job['job_id'])
                from .context_routing import apply as route_families,CONTEXT
                save(stage="브라스·기타 성분 정리 중",progress=96.8)
                row=route_families(self.root,row,{h:context_sources[h] for h in CONTEXT.values()},context_job['job_id'])
            if row["model"]=="final_10":
                from .synth_recovery import run_for_library
                recoveries=(("synth",85,"신디사이저 보완 추출 중"),("strings",91,"스트링 보완 추출 중"))
                for family,base,stage in recoveries:
                    row.update(state="RUNNING",stage=stage,progress=base,active_job_id=None,completed_chunks=0,total_chunks=0)
                    write_json(folder/"record.json",row)
                    def recovery_progress(p):
                        fraction=p["completed"]/max(1,p["total"])
                        save(progress=round(max(row["progress"],base+5.8*fraction),1),completed_chunks=p["completed"],total_chunks=p["total"])
                    row=run_for_library(self,row,family,on_progress=recovery_progress)
            if is11:
                save(stage="최종 반주 정리",progress=97,completed_chunks=0,total_chunks=0)
                final_tracks=[t for t in row["tracks"] if t["family"]!="other"]
                row=self.with_remaining(row,final_tracks,"flat_v4","remaining-final11-v3.wav",row["instrumental"],
                                        [t for t in final_tracks if t["family"] not in ("lead","backing")])
            save(stage="최종 결과 저장",progress=98,completed_chunks=0,total_chunks=0)
            if row["model"]=="final_10":
                from .leakage_rule import apply as apply_leakage_rule
                save(stage="악기 누출 억제 및 결과 검증 중",progress=97)
                row=apply_leakage_rule(self.root,row)
            if final:
                self.validate_partition(row["instrumental"],[t for t in row["tracks"] if t["family"] not in ("lead","backing")])
            if is11:self.validate_partition(row["original"],row["tracks"])
            tracks=[self.track_activity(t) for t in row["tracks"]]
            save(state="SUCCEEDED",stage="분석 완료",progress=100,tracks=tracks,
                 original=str((asset/"canonical.wav").relative_to(self.root)),active_job_id=None)
        except Exception as error:
            upload.unlink(missing_ok=True)
            save(state="FAILED",stage="분석 실패",error=str(error),active_job_id=None)

    def delete(self,identifier):
        """Remove one analysis and every job/asset directory no other analysis or job still uses."""
        if not re.fullmatch(r"analysis_[0-9a-f]{32}",identifier):raise ValueError("잘못된 분석 ID입니다.")
        folder=self.web/identifier
        row=read_json(folder/"record.json")
        if row.get("state") in BUSY_STATES:raise ValueError("진행 중인 분석은 완료된 뒤에 삭제할 수 있습니다.")
        mine=stored_ids(json.dumps(row))
        kept=set()
        for path in (*self.web.glob("analysis_*/record.json"),*(self.root/"pipelines").glob("*/manifest.json")):
            if path.parent.name!=identifier:kept|=stored_ids(path.read_text(encoding="utf-8",errors="replace"))
        doomed_jobs={x for x in mine if x.startswith("job_")}-kept
        mine_assets={x for x in mine if x.startswith("asset_")}
        kept_assets={x for x in kept if x.startswith("asset_")}
        for path in (self.root/"jobs").glob("job_*/job.json"):
            try:assets={x for x in stored_ids(path.read_text(encoding="utf-8",errors="replace")) if x.startswith("asset_")}
            except OSError:continue
            if path.parent.name in doomed_jobs:mine_assets|=assets
            else:kept_assets|=assets
        doomed=[self.root/"jobs"/x for x in doomed_jobs]+[self.root/"inputs"/x for x in mine_assets-kept_assets]
        doomed+=[self.web/sub/identifier for sub in ("previews","enhanced","bundles")]+list((self.web/"archives").glob(identifier+"_*.zip"))
        with self.cache_lock:
            for path in doomed:
                if path.is_dir() and not path.is_symlink():shutil.rmtree(path)
                elif path.exists():path.unlink()
            shutil.rmtree(folder)
            for key in [k for k in self.gain_cache if k[0]==identifier]:self.gain_cache.pop(key)

    def delete_many(self,identifiers):
        """All-or-nothing busy check, then delete; missing records are already gone."""
        identifiers=list(identifiers)
        for identifier in identifiers:
            try:
                if read_json(self.web/identifier/"record.json").get("state") in BUSY_STATES:raise ValueError("진행 중인 분석이 있습니다. 분석이 끝난 뒤 다시 시도해 주세요.")
            except FileNotFoundError:pass
        for identifier in identifiers:
            try:self.delete(identifier)
            except FileNotFoundError:pass

    def validate_partition(self,source_path,tracks):
        import contextlib
        with contextlib.ExitStack() as stack:
            source=stack.enter_context(sf.SoundFile(self.safe(source_path)))
            inputs=[stack.enter_context(sf.SoundFile(self.safe(t["path"]))) for t in tracks]
            if (source.samplerate,source.channels)!=(RATE,2) or any((f.frames,f.samplerate,f.channels)!=(source.frames,RATE,2) for f in inputs):raise ValueError("최종 트랙 길이가 일치하지 않습니다.")
            for block in source.blocks(blocksize=RATE,dtype="float32",always_2d=True):
                total=np.zeros(block.shape,dtype=np.float64)
                for f in inputs:total+=f.read(len(block),dtype="float32",always_2d=True)
                if not np.isfinite(block).all() or not np.isfinite(total).all() or np.max(np.abs(total-block))>2e-6:raise ValueError("최종 트랙 합계 검증 실패")

    def flatten_session(self,row):
        """Keep the original instrument parents and only split vocal performances."""
        source={t["family"]:t for t in row["tracks"]}
        if not {"lead","backing","other","guitar"}.issubset(source):return row
        tracks=[]
        for family in ("lead","backing","piano","other","guitar","bass","drums"):
            if family not in source:continue
            track={k:v for k,v in source[family].items() if k not in ("parent_family","display_name")}
            if family=="other":track["family"]="synth"
            tracks.append(track)
        return self.with_remaining(row,tracks,"flat_v1","remaining-v1.wav")

    def final_session(self,row):
        source={t["family"]:t for t in row["tracks"]}
        order=(("lead","lead"),("backing","backing"),("piano","piano"),("synth","synth"),
               ("bowed_strings","strings"),("brass","brass"),("acoustic-guitar","acoustic_guitar"),("electric-guitar","guitar"),
               ("bass","bass"),("drums","drums"))
        if any(key not in source for key,_ in order):raise ValueError("최종 트랙에 필요한 악기 출력이 누락됐습니다.")
        tracks=[{**{k:v for k,v in source[key].items() if k not in ("parent_family","display_name")},"family":family} for key,family in order]
        if row.get("separation_version") in ("staged-guitar-residual-v8","staged-guitar-residual-v9","staged-guitar-residual-v10","staged-context-percussion-v11","staged-context-percussion-v12","staged-context-strings-v13","staged-context-backing-v14","staged-context-families-v15","staged-context-pads-v16","commercial-13-v1"):
            tracks.append(source["guitar_residual"])
        return self.with_remaining(row,tracks,"flat_v4","remaining-v4.wav",row["instrumental"],
                                   [t for t in tracks if t["family"] not in ("lead","backing")])

    def with_remaining(self,row,tracks,layout,filename,residual_source=None,residual_tracks=None):
        folder=self.web/row["id"];folder.mkdir(parents=True,exist_ok=True)
        remaining=folder/filename
        peak=0.
        if not remaining.exists():
            import contextlib
            with contextlib.ExitStack() as stack:
                original=stack.enter_context(sf.SoundFile(self.safe(residual_source or row["original"])))
                inputs=[stack.enter_context(sf.SoundFile(self.safe(t["path"]))) for t in (tracks if residual_tracks is None else residual_tracks)]
                if any((f.frames,f.samplerate,f.channels)!=(original.frames,original.samplerate,original.channels) for f in inputs):
                    raise ValueError("잔여 트랙 생성 시 음원 길이가 일치하지 않습니다.")
                output=stack.enter_context(sf.SoundFile(remaining.with_suffix(".partial.wav"),"w",samplerate=original.samplerate,channels=original.channels,subtype="FLOAT"))
                for block in original.blocks(blocksize=44100,dtype="float32",always_2d=True):
                    residual=block.astype(np.float64)
                    for input_file in inputs:residual-=input_file.read(len(block),dtype="float32",always_2d=True)
                    peak=max(peak,float(np.abs(residual).max()))
                    output.write(residual.astype(np.float32))
            remaining.with_suffix(".partial.wav").replace(remaining)
        else:
            with sf.SoundFile(remaining) as source:
                for block in source.blocks(blocksize=44100,dtype="float32",always_2d=True):peak=max(peak,float(np.abs(block).max()))
        tracks.append({"family":"other","path":str(remaining.relative_to(self.root)),"sha256":sha256_file(remaining),"peak":peak})
        row=dict(row,tracks=tracks,track_layout=layout)
        row.pop("track_note",None)
        row.pop("groups",None)
        return row

    def track_path(self,row,family):
        if family=="original":return self.safe(row["original"])
        for track in row["tracks"]:
            if track["family"]==family:return self.safe(track["path"])
        raise FileNotFoundError("트랙을 찾을 수 없습니다.")

    @staticmethod
    def output_silent(track):
        """Shared near-silence policy; cached measurements also cover old results."""
        if "signal_rms" in track and "peak" in track:
            return track["peak"]<=.002 and track["signal_rms"]<=.00005
        return track.get("silent",False)

    def track_activity(self,track):
        """Hide negligible output across all families; not an instrument classifier."""
        if "signal_rms" in track and "peak" in track:
            return {**track,"silent":self.output_silent(track)}
        peak=energy=0.;samples=0
        with sf.SoundFile(self.safe(track["path"])) as source:
            for block in source.blocks(blocksize=44100,dtype="float32",always_2d=True):
                peak=max(peak,float(np.abs(block).max()))
                energy+=float(np.sum(block.astype(np.float64)**2));samples+=block.size
        rms=float(np.sqrt(energy/max(1,samples)))
        measured={**track,"signal_rms":rms,"peak":peak}
        return {**measured,"silent":self.output_silent(measured)}

    def detail(self,identifier):
        row=self.get(identifier)
        if row["state"]!="SUCCEEDED":return self.public(row)
        tracks=[]
        for t in row["tracks"]:
            if self.track_activity(t)["silent"]:continue
            path=self.track_path(row,t["family"])
            with sf.SoundFile(path) as source:
                frames=source.frames
                size=max(1,int(np.ceil(frames/1200)))
                peaks=[]
                for block in source.blocks(blocksize=size,dtype="float32",always_2d=True):
                    peaks.append(round(float(np.abs(block).max()),5))
            tracks.append({"family":t["family"],"display_name":t.get("display_name"),"parent_family":t.get("parent_family"),"waveform":peaks,"peak":t.get("peak",1),
                           "url":f"/api/analyses/{identifier}/audio/{t['family']}",
                           "download":f"/api/analyses/{identifier}/download/{t['family']}"})
        original_peaks=[]
        with sf.SoundFile(self.track_path(row,"original")) as source:
            size=max(1,int(np.ceil(source.frames/1200)))
            for block in source.blocks(blocksize=size,dtype="float32",always_2d=True):original_peaks.append(round(float(np.abs(block).max()),5))
        return self.public(row)|{"track_count":len(tracks),"tracks":tracks,"original_waveform":original_peaks,"original_url":f"/api/analyses/{identifier}/audio/original",
            "archive_url":f"/api/analyses/{identifier}/archive","preview_note":"재생용 음량 조절은 다운로드 WAV에 반영되지 않습니다."}

    def fingerprint(self,row):
        return hashlib.sha256(json.dumps([(t["family"],t.get("sha256",t["path"])) for t in row["tracks"]]).encode()).hexdigest()[:16]

    def preview(self,row,family):
        folder=self.web/"previews"/row["id"]/self.fingerprint(row)
        compressed=row.get("duration",0)>120
        target=folder/(family+(".flac" if compressed else ".wav"))
        with self.cache_lock:
            if not target.exists():
                folder.mkdir(parents=True,exist_ok=True)
                maximum=max(1.,max(t.get("peak",1) for t in row["tracks"]))
                # Include original full-scale overshoot in shared playback gain.
                source_path=self.track_path(row,"original")
                with sf.SoundFile(source_path) as original:
                    for block in original.blocks(blocksize=RATE*10,dtype="float32",always_2d=True):
                        maximum=max(maximum,float(np.abs(block).max()))
                gain=min(1.,.9/maximum)
                partial=target.with_suffix(".partial")
                with sf.SoundFile(self.track_path(row,family)) as source,sf.SoundFile(partial,"w",samplerate=RATE,channels=2,format="FLAC" if compressed else "WAV",subtype="PCM_16") as output:
                    for block in source.blocks(blocksize=RATE*10,dtype="float32",always_2d=True):output.write(block*np.float32(gain))
                partial.replace(target)
        return target

    def audio_window(self,row,family,start,count):
        if start<0 or not 0<count<=RATE*30:raise ValueError('Invalid playback window')
        key=(row['id'],self.fingerprint(row))
        with self.cache_lock:
            if key not in self.gain_cache:
                maximum=max(1.,max(t.get('peak',1) for t in row['tracks']))
                with sf.SoundFile(self.track_path(row,'original')) as source:
                    for block in source.blocks(blocksize=RATE*10,dtype='float32',always_2d=True):maximum=max(maximum,float(np.abs(block).max()))
                self.gain_cache[key]=min(1.,.9/maximum)
            gain=self.gain_cache[key]
        with sf.SoundFile(self.track_path(row,family)) as source:
            if start>=source.frames:raise ValueError('Playback position exceeds track length')
            source.seek(start);samples=source.read(count,dtype='float32',always_2d=True)
            output=io.BytesIO()
            sf.write(output,samples*np.float32(gain),source.samplerate,format='WAV',subtype='PCM_16')
            return output.getvalue()

    def enhanced(self,row,family,strength):
        from scipy.signal import sosfilt
        profiles={"vocals":((300,-1.5,.8),(3200,1.3,.7)),"guitar":((320,-1.4,.8),(2600,1.2,.7)),"piano":((280,-1.2,.8),(3000,1,.7)),"bass":((300,-.7,.8),(1200,.6,.7)),"drums":((350,-.8,.8),(4500,.8,.7)),"other":((350,-.6,.7),(3000,.5,.7))}
        profiles.update(lead=profiles["vocals"],backing=profiles["vocals"],synth=profiles["other"],brass=profiles["other"],strings=profiles["other"],acoustic_guitar=profiles["guitar"],synth_pad=profiles["other"],other_residual=profiles["other"],lead_guitar=profiles["guitar"],guitar_residual=profiles["guitar"])
        if family not in profiles:raise ValueError("후처리를 지원하지 않는 트랙입니다.")
        if not 0<=strength<=100:raise ValueError("강도는 0–100입니다.")
        folder=self.web/"enhanced"/row["id"]/self.fingerprint(row);target=folder/(family+f"-clarity-v1-{strength}.wav")
        with self.cache_lock:
            if target.exists():return target
            folder.mkdir(parents=True,exist_ok=True)
            sos=[]
            for frequency,gain,q in profiles[family]:
                A=10**(gain*strength/50/40);w=2*np.pi*frequency/RATE;alpha=np.sin(w)/(2*q);c=np.cos(w)
                sos.append([1+alpha*A,-2*c,1-alpha*A,1+alpha/A,-2*c,1-alpha/A])
            sos=np.asarray(sos);sos[:,:3]/=sos[:,3,None];sos[:,4:]/=sos[:,3,None];sos[:,3]=1
            state=np.zeros((len(sos),2,2));partial=target.with_suffix(".partial")
            try:
                with sf.SoundFile(self.track_path(row,family)) as source,sf.SoundFile(partial,"w",samplerate=source.samplerate,channels=source.channels,format="WAV",subtype="FLOAT") as output:
                    for block in source.blocks(blocksize=RATE*5,dtype="float64",always_2d=True):
                        processed,state=sosfilt(sos,block,axis=0,zi=state);output.write(processed)
                partial.replace(target)
            finally:
                if partial.exists():partial.unlink()
        return target

    def bundle(self,row,mode,settings):
        if mode not in ("enhanced","both"):raise ValueError("다운로드 종류가 잘못되었습니다.")
        families={t["family"] for t in row["tracks"]}
        if not isinstance(settings,dict) or not settings or not set(settings)<=families:raise ValueError("트랙 선택이 잘못되었습니다.")
        if any(type(value) is not int or not 0<=value<=100 for value in settings.values()):raise ValueError("강도는 0–100입니다.")
        key=hashlib.sha256(json.dumps([mode,settings],sort_keys=True).encode()).hexdigest()[:16]
        folder=self.web/"bundles"/row["id"]/self.fingerprint(row);folder.mkdir(parents=True,exist_ok=True)
        target=folder/(key+"-v1.zip")
        if target.exists():return target
        processed={family:self.enhanced(row,family,strength) for family,strength in settings.items()}
        with self.cache_lock:
            if not target.exists():
                partial=target.with_suffix(".partial")
                try:
                    with zipfile.ZipFile(partial,"w",zipfile.ZIP_STORED) as archive:
                        for family,path in processed.items():
                            archive.write(path,f"clarity/{family}-clarity-{settings[family]}.wav")
                            if mode=="both":archive.write(self.track_path(row,family),f"raw/{family}.wav")
                        archive.writestr("settings.json",json.dumps({"mode":mode,"strengths":settings,"version":1},ensure_ascii=False))
                    partial.replace(target)
                finally:
                    if partial.exists():partial.unlink()
        return target

    def archive(self,row):
        folder=self.web/"archives";folder.mkdir(exist_ok=True)
        target=folder/(row["id"]+"_"+self.fingerprint(row)+".zip")
        with self.cache_lock:
            if not target.exists():
                partial=target.with_suffix(".partial")
                with zipfile.ZipFile(partial,"w",compression=zipfile.ZIP_STORED) as archive:
                    for t in row["tracks"]:archive.write(self.track_path(row,t["family"]),t["family"]+".wav")
                    archive.writestr("manifest.json",json.dumps(self.public(row),ensure_ascii=False,indent=2))
                partial.replace(target)
        return target

def make_handler(library,dist,port,public_access=False,auth=None):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def json(self,status,data,cookie=None):
            body=json.dumps(data,ensure_ascii=False).encode()
            self.send_response(status);self.send_header("Content-Type","application/json; charset=utf-8")
            self.send_header("Content-Length",str(len(body)));self.send_header("Cache-Control","no-store")
            if cookie:self.send_header("Set-Cookie",cookie)
            self.end_headers();self.wfile.write(body)
        def session_token(self):
            cookie=SimpleCookie()
            try:cookie.load(self.headers.get("Cookie",""))
            except CookieError:return ""
            return cookie[COOKIE_NAME].value if COOKIE_NAME in cookie else ""
        def cookie(self,token,clear=False):
            return f"{COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={0 if clear else SESSION_SECONDS}"+("; Secure" if auth.secure_cookie else "")
        def user(self):
            if auth is None:raise DatabaseUnavailable("회원 DB 설정이 필요합니다.")
            user=auth.session_user(self.session_token())
            if not user:raise AuthError("로그인이 필요합니다.",401)
            return user
        def member(self,user):
            return {**user,"consent_required":not auth.has_current_consents(user["id"])}
        def consented(self,user):
            if not auth.has_current_consents(user["id"]):raise AuthError("현재 이용약관과 개인정보 수집·이용에 동의해야 이용할 수 있습니다.",403)
        def authorize(self,user,identifier):
            if not auth.owns(user["id"],identifier):raise FileNotFoundError("분석을 찾을 수 없습니다.")
        def allowed(self):
            host=self.headers.get("Host","").split(":")[0]
            origin=self.headers.get("Origin")
            if public_access:
                authority=self.headers.get("Host","")
                return bool(authority) and (not origin or origin in ("http://"+authority,"https://"+authority))
            return host in ("127.0.0.1","localhost") and (not origin or origin in (f"http://127.0.0.1:{port}",f"http://localhost:{port}","http://localhost:5173","http://127.0.0.1:5173"))
        def do_POST(self):
            if not self.allowed():return self.json(403,{"error":"허용되지 않는 요청입니다."})
            if self.headers.get("X-Requested-With")!="MusicAnalyzer":return self.json(403,{"error":"허용되지 않는 요청입니다."})
            try:
                if auth is None:raise DatabaseUnavailable("회원 DB 설정이 필요합니다.")
                path=urllib.parse.urlsplit(self.path).path
                if path in ("/api/auth/register","/api/auth/login"):
                    auth.throttle(self.client_address[0])
                    length=int(self.headers.get("Content-Length","0"))
                    if not 0<length<=8192:raise ValueError("잘못된 요청 크기입니다.")
                    data=json.loads(self.rfile.read(length))
                    user=auth.register(data) if path.endswith("register") else auth.login(data)
                    user=self.member(user)
                    auth.logout(self.session_token())
                    token=auth.new_session(user["id"])
                    return self.json(201 if path.endswith("register") else 200,{"user":user},self.cookie(token))
                if path=="/api/auth/logout":
                    auth.logout(self.session_token())
                    return self.json(200,{"ok":True},self.cookie("",True))
                user=self.user()
                if path=="/api/auth/consent":
                    length=int(self.headers.get("Content-Length","0"))
                    if not 0<length<=8192:raise ValueError("잘못된 요청 크기입니다.")
                    try:auth.record_consents(user["id"],require_consents(json.loads(self.rfile.read(length)).get("consents")))
                    except ConsentError as error:raise AuthError(str(error)) from None
                    return self.json(200,{"ok":True})
                self.consented(user)
                match=re.fullmatch(r"/api/analyses/([^/]+)/vocal-detail",path)
                if match:
                    self.authorize(user,match[1])
                    return self.json(202,library.create_vocal_detail(match[1],claim=lambda identifier:auth.assign(user["id"],identifier),visible=lambda identifier:auth.owns(user["id"],identifier)))
                if path!="/api/analyses":return self.json(404,{"error":"없는 경로입니다."})
                query=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                name=urllib.parse.unquote(self.headers.get("X-Filename",""))
                result=library.create(name,query.get("preset",["final_10"])[0],self.rfile,int(self.headers.get("Content-Length","0")),claim=lambda identifier:auth.assign(user["id"],identifier),rights=query.get("rights",[""])[0])
                self.json(202,result)
            except AuthError as error:self.json(error.status,{"error":str(error)})
            except DatabaseUnavailable as error:self.json(503,{"error":str(error)})
            except FileNotFoundError:self.json(404,{"error":"분석을 찾을 수 없습니다."})
            except (ValueError,OSError) as error:self.json(400,{"error":str(error)})
        def do_DELETE(self):
            if not self.allowed() or self.headers.get("X-Requested-With")!="MusicAnalyzer":return self.json(403,{"error":"허용되지 않는 요청입니다."})
            path=urllib.parse.urlsplit(self.path).path
            try:
                user=self.user()
                if path=="/api/auth/account":
                    library.delete_many(auth.owned_ids(user["id"]))
                    auth.delete_account(user["id"])
                    return self.json(200,{"ok":True},self.cookie("",True))
                match=re.fullmatch(r"/api/analyses/([^/]+)",path)
                if not match:return self.json(404,{"error":"없는 경로입니다."})
                self.authorize(user,match[1])
                try:library.delete(match[1])
                except FileNotFoundError:pass  # record already gone (interrupted earlier delete): finish by releasing ownership
                auth.release(match[1])
                self.json(200,{"ok":True})
            except AuthError as error:self.json(error.status,{"error":str(error)})
            except DatabaseUnavailable as error:self.json(503,{"error":str(error)})
            except FileNotFoundError:self.json(404,{"error":"분석을 찾을 수 없습니다."})
            except (ValueError,OSError) as error:self.json(400,{"error":str(error)})
        def file(self,path,download=None):
            size=path.stat().st_size
            start,end=0,size-1
            header=self.headers.get("Range","")
            if header:
                match=re.fullmatch(r"bytes=(\d+)-(\d*)",header)
                if not match:return self.json(416,{"error":"잘못된 범위"})
                start=int(match[1]);end=min(size-1,int(match[2])) if match[2] else size-1
                if start>end:return self.json(416,{"error":"잘못된 범위"})
            self.send_response(206 if header else 200)
            self.send_header("Content-Type",({".flac":"audio/flac",".mp3":"audio/mpeg",".wav":"audio/wav"}.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"))
            self.send_header("Content-Length",str(end-start+1));self.send_header("Accept-Ranges","bytes")
            self.send_header("Cache-Control","private, no-store")
            self.send_header("X-Content-Type-Options","nosniff")
            if header:self.send_header("Content-Range",f"bytes {start}-{end}/{size}")
            if download:self.send_header("Content-Disposition","attachment; filename*=UTF-8''"+urllib.parse.quote(download))
            self.end_headers()
            with path.open("rb") as source:
                source.seek(start);remaining=end-start+1
                while remaining:
                    block=source.read(min(1024**2,remaining))
                    if not block:break
                    self.wfile.write(block);remaining-=len(block)
        def do_GET(self):
            if not self.allowed():return self.json(403,{"error":"허용되지 않는 요청입니다."})
            path=urllib.parse.urlsplit(self.path).path
            try:
                if path=="/api/legal":return self.json(200,public_versions())
                if path=="/api/release":return self.json(200,release.public_status())
                if path=="/api/auth/me":return self.json(200,{"user":self.member(self.user())})
                if path.startswith("/api/"):user=self.user();self.consented(user)
                if path=="/api/analyses":
                    owned=auth.owned_ids(user["id"])
                    return self.json(200,[library.public(r) for r in library.entries(owned)])
                match=re.fullmatch(r"/api/analyses/([^/]+)(?:/(audio|download|archive|enhanced|bundle)(?:/([a-z][a-z0-9_]*))?)?",path)
                if match:
                    identifier,action,family=match.groups()
                    self.authorize(user,identifier)
                    if not action:return self.json(200,library.detail(identifier))
                    row=library.get(identifier)
                    if row["state"]!="SUCCEEDED":raise ValueError("분석이 아직 완료되지 않았습니다.")
                    if action=="bundle":
                        query=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                        return self.file(library.bundle(row,query.get("mode",[""])[0],json.loads(query.get("settings",["{}"]) [0])),row["name"]+"-tracks.zip")
                    if action=="enhanced":
                        strength=int(urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("strength",["50"])[0])
                        return self.file(library.enhanced(row,family,strength),family+f"-clarity-{strength}.wav")
                    if action=="archive":return self.file(library.archive(row),row["name"]+"-stems.zip")
                    if action=="download":return self.file(library.track_path(row,family),family+".wav")
                    query=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                    if 'start_frame' in query or 'num_frames' in query:
                        body=library.audio_window(row,family,int(query.get('start_frame',['0'])[0]),int(query.get('num_frames',[str(RATE*30)])[0]))
                        self.send_response(200);self.send_header('Content-Type','audio/wav');self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','private, no-store');self.end_headers();self.wfile.write(body);return
                    return self.file(library.preview(row,family))
                if path.startswith("/api/"):return self.json(404,{"error":"없는 경로입니다."})
                target=(dist/path.lstrip("/")).resolve()
                if not target.is_relative_to(dist.resolve()):return self.json(403,{"error":"허용되지 않는 경로"})
                if not target.is_file():target=dist/"index.html"
                return self.file(target)
            except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass
            except AuthError as error:self.json(error.status,{"error":str(error)})
            except DatabaseUnavailable as error:self.json(503,{"error":str(error)})
            except FileNotFoundError as error:self.json(404,{"error":str(error)})
            except (ValueError,KeyError,OSError) as error:self.json(400,{"error":str(error)})
            except (BrokenPipeError,ConnectionResetError):pass
    return Handler

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--port",type=int,default=8780)
    parser.add_argument("--host",default="127.0.0.1")
    parser.add_argument("--public-access",action="store_true",help="Allow external Host headers; requires explicit network exposure")
    parser.add_argument("--data-root",type=Path,default=project_root()/"data/separation")
    args=parser.parse_args()
    try:print("release profile: "+release.startup_check(args.data_root),flush=True)
    except release.ReleaseError as error:raise SystemExit("refusing to start: "+error.detail)
    auth=AuthStore()
    auth.check()
    library=WebLibrary(args.data_root)
    dist=project_root()/"frontend/dist"
    server=ThreadingHTTPServer((args.host,args.port),make_handler(library,dist,args.port,args.public_access,auth=auth))
    print(f"http://127.0.0.1:{args.port}",flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        library.stopping.set()
        server.server_close()
        for r in library.entries():
            if r.get("active_job_id"):
                try:JobService(library.root).cancel(r["active_job_id"])
                except Exception:pass
        library.executor.shutdown(wait=True,cancel_futures=True)

if __name__=="__main__":main()
