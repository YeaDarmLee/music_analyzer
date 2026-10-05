"""Loopback-only web API and built Vue frontend. No external audio uploads."""
from __future__ import annotations
import argparse,hashlib,json,mimetypes,re,shutil,threading,time,urllib.parse,zipfile
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4
import numpy as np
import soundfile as sf
from .common import project_root,read_json,write_json,sha256_file
from .ingest import ingest_file,load_asset
from .job_service import JobService
from .job_contracts import job_folder,verify_result,JobError
from .audio import RATE

class WebLibrary:
    def __init__(self,root):
        self.root=Path(root).resolve()
        self.web=self.root/"web"
        self.web.mkdir(parents=True,exist_ok=True)
        self.executor=ThreadPoolExecutor(max_workers=1)
        self.cache_lock=threading.Lock()
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

    def entries(self):
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
        for row in self.entries():
            if row["id"]==identifier:return row
        raise FileNotFoundError("분석을 찾을 수 없습니다.")

    def public(self,row):
        return {k:v for k,v in row.items() if k not in ("tracks","original","job_ids","input_path")}|{"track_count":len(row.get("tracks",[]))}

    def create(self,filename,preset,stream,length):
        if preset not in ("instrument_roformer_6s","quality_6s"): raise ValueError("지원하지 않는 모델입니다.")
        extension=Path(filename).suffix.lower()
        if extension not in (".mp3",".wav",".flac"): raise ValueError("MP3, WAV, FLAC 파일을 선택해 주세요.")
        if not 0<length<=1024**3:raise ValueError("파일은 1GB 이하여야 합니다.")
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
             "model":preset,"duration":0,"tracks":[],"job_ids":[],"vocal_source":"roformer","secondary_vocals_excluded":True}
        write_json(folder/"record.json",row)
        self.executor.submit(self.analyze,folder,upload,row)
        return self.public(row)

    def analyze(self,folder,upload,row):
        service=JobService(self.root)
        def save(**values):
            row.update(values);write_json(folder/"record.json",row)
        def update(job,base,span,stage):
            p=job.get("progress") or {}
            fraction=p.get("completed",0)/max(1,p.get("total",0)) if p.get("total") else 0
            percent=max(row["progress"],min(97,base+span*fraction))
            save(state="RUNNING",stage=stage,progress=round(percent),active_job_id=job["job_id"],
                 completed_chunks=p.get("completed",0),total_chunks=p.get("total",0))
        def run_stage(asset_id,preset_name,callback):
            while not self.stopping.is_set():
                try:return service.run(asset_id,preset_name,callback)
                except JobError as error:
                    if error.code!="GPU_BUSY":raise
                    save(state="QUEUED",stage="다른 음원 처리 완료를 기다리는 중")
                    self.stopping.wait(1)
            raise ValueError("서버 종료로 분석이 중단됐습니다.")
        try:
            save(state="RUNNING",stage="음원 확인 및 변환",progress=2)
            asset=ingest_file(upload,self.root)
            original=load_asset(self.root,asset.name)
            save(duration=original["timeline"]["num_frames"]/RATE,progress=5)
            vocal=run_stage(asset.name,"vocal_roformer",lambda j:update(j,5,40,"보컬 분리 중"))
            row["job_ids"].append(vocal["job_id"])
            if vocal["state"]!="SUCCEEDED":raise ValueError("보컬 분리를 완료하지 못했습니다: "+vocal["state"])
            first_dir=job_folder(self.root,vocal["job_id"])/"result"
            first=verify_result(first_dir,vocal)
            instrumental=next(s for s in first["stems"] if s["family"]=="instrumental")
            save(stage="악기 분리 준비",progress=47)
            second_asset=ingest_file(first_dir/instrumental["path"],self.root)
            second=run_stage(second_asset.name,row["model"],lambda j:update(j,50,45,"악기 분리 중"))
            row["job_ids"].append(second["job_id"])
            if second["state"]!="SUCCEEDED":raise ValueError("악기 분리를 완료하지 못했습니다: "+second["state"])
            second_dir=job_folder(self.root,second["job_id"])/"result"
            second_result=verify_result(second_dir,second)
            tracks=[]
            for base,stems in [(first_dir,[s for s in first["stems"] if s["family"]=="vocals"]),
                               (second_dir,[s for s in second_result["stems"] if s["family"]!="vocals"])]:
                tracks.extend({**s,"path":str((base/s["path"]).relative_to(self.root))} for s in stems)
            save(state="SUCCEEDED",stage="분석 완료",progress=100,tracks=tracks,
                 original=str((asset/"canonical.wav").relative_to(self.root)),active_job_id=None)
        except Exception as error:
            save(state="FAILED",stage="분석 실패",error=str(error),active_job_id=None)

    def track_path(self,row,family):
        if family=="original":return self.safe(row["original"])
        for track in row["tracks"]:
            if track["family"]==family:return self.safe(track["path"])
        raise FileNotFoundError("트랙을 찾을 수 없습니다.")

    def detail(self,identifier):
        row=self.get(identifier)
        if row["state"]!="SUCCEEDED":return self.public(row)
        tracks=[]
        for t in row["tracks"]:
            path=self.track_path(row,t["family"])
            with sf.SoundFile(path) as source:
                frames=source.frames
                size=max(1,int(np.ceil(frames/1200)))
                peaks=[]
                for block in source.blocks(blocksize=size,dtype="float32",always_2d=True):
                    peaks.append(round(float(np.abs(block).max()),5))
            tracks.append({"family":t["family"],"waveform":peaks,"peak":t.get("peak",1),
                           "url":f"/api/analyses/{identifier}/audio/{t['family']}",
                           "download":f"/api/analyses/{identifier}/download/{t['family']}"})
        return self.public(row)|{"tracks":tracks,"original_url":f"/api/analyses/{identifier}/audio/original",
            "archive_url":f"/api/analyses/{identifier}/archive","preview_note":"재생용 음량 조절은 다운로드 WAV에 반영되지 않습니다."}

    def fingerprint(self,row):
        return hashlib.sha256(json.dumps([(t["family"],t.get("sha256",t["path"])) for t in row["tracks"]]).encode()).hexdigest()[:16]

    def preview(self,row,family):
        folder=self.web/"previews"/row["id"]/self.fingerprint(row)
        target=folder/(family+".wav")
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
                with sf.SoundFile(self.track_path(row,family)) as source,sf.SoundFile(partial,"w",samplerate=RATE,channels=2,format="WAV",subtype="PCM_16") as output:
                    for block in source.blocks(blocksize=RATE*10,dtype="float32",always_2d=True):output.write(block*np.float32(gain))
                partial.replace(target)
        return target

    def enhanced(self,row,family,strength):
        from scipy.signal import sosfilt
        profiles={"vocals":((300,-1.5,.8),(3200,1.3,.7)),"guitar":((320,-1.4,.8),(2600,1.2,.7)),"piano":((280,-1.2,.8),(3000,1,.7)),"bass":((300,-.7,.8),(1200,.6,.7)),"drums":((350,-.8,.8),(4500,.8,.7)),"other":((350,-.6,.7),(3000,.5,.7))}
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

def make_handler(library,dist,port,public_access=False):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def json(self,status,data):
            body=json.dumps(data,ensure_ascii=False).encode()
            self.send_response(status);self.send_header("Content-Type","application/json; charset=utf-8")
            self.send_header("Content-Length",str(len(body)));self.send_header("Cache-Control","no-store")
            self.end_headers();self.wfile.write(body)
        def allowed(self):
            host=self.headers.get("Host","").split(":")[0]
            origin=self.headers.get("Origin")
            if public_access:
                authority=self.headers.get("Host","")
                return bool(authority) and (not origin or origin in ("http://"+authority,"https://"+authority))
            return host in ("127.0.0.1","localhost") and (not origin or origin in (f"http://127.0.0.1:{port}",f"http://localhost:{port}","http://localhost:5173","http://127.0.0.1:5173"))
        def do_POST(self):
            if not self.allowed():return self.json(403,{"error":"허용되지 않는 요청입니다."})
            if self.path.split("?")[0]!="/api/analyses":return self.json(404,{"error":"없는 경로입니다."})
            try:
                query=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                name=urllib.parse.unquote(self.headers.get("X-Filename",""))
                result=library.create(name,query.get("preset",["instrument_roformer_6s"])[0],self.rfile,int(self.headers.get("Content-Length","0")))
                self.json(202,result)
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
            self.send_header("Content-Type",mimetypes.guess_type(path.name)[0] or "application/octet-stream")
            self.send_header("Content-Length",str(end-start+1));self.send_header("Accept-Ranges","bytes")
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
                if path=="/api/analyses":return self.json(200,[library.public(r) for r in library.entries()])
                match=re.fullmatch(r"/api/analyses/([^/]+)(?:/(audio|download|archive|enhanced|bundle)(?:/([a-z]+))?)?",path)
                if match:
                    identifier,action,family=match.groups()
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
                    return self.file(library.preview(row,family))
                if path.startswith("/api/"):return self.json(404,{"error":"없는 경로입니다."})
                target=(dist/path.lstrip("/")).resolve()
                if not target.is_relative_to(dist.resolve()):return self.json(403,{"error":"허용되지 않는 경로"})
                if not target.is_file():target=dist/"index.html"
                return self.file(target)
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
    library=WebLibrary(args.data_root)
    dist=project_root()/"frontend/dist"
    server=ThreadingHTTPServer((args.host,args.port),make_handler(library,dist,args.port,args.public_access))
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
