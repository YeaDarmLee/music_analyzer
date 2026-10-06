"""Run using the project's .venv Python. Prepares an isolated AudioSep environment."""
from pathlib import Path
import hashlib, json, subprocess, urllib.request, venv
root=Path(__file__).resolve().parents[1]
registration=json.loads((root/"separation/configs/models/audiosep_base.json").read_text(encoding="utf-8"))
repo=root/"data/separation/tools/AudioSep";env=root/"data/separation/tools/audiosep-env"
if not repo.exists():subprocess.run(["git","clone","--depth","1",registration["repository_url"],str(repo)],check=True)
if subprocess.check_output(["git","-c","safe.directory="+str(repo),"rev-parse","HEAD"],cwd=repo,text=True).strip()!=registration["code_revision"]:
    subprocess.run(["git","-c","safe.directory="+str(repo),"fetch","origin",registration["code_revision"]],cwd=repo,check=True)
    subprocess.run(["git","-c","safe.directory="+str(repo),"checkout","--detach",registration["code_revision"]],cwd=repo,check=True)
if not (env/"Scripts/python.exe").exists():venv.EnvBuilder(with_pip=True).create(env)
(env/"Lib/site-packages/music_analyzer_base.pth").write_text(str(root/".venv/Lib/site-packages")+"\n"+str(root/"separation/src")+"\n",encoding="utf-8")
python=str(env/"Scripts/python.exe")
subprocess.run([python,"-m","pip","install","lightning==2.5.0","transformers==4.44.2","torchlibrosa==0.1.0","timm==0.9.16","torchvision==0.20.1","webdataset==0.2.111","ftfy==6.3.1","braceexpand==0.1.7","wget==3.2","h5py==3.16.0","pandas==3.0.6","--extra-index-url","https://download.pytorch.org/whl/cu121"],check=True)
for artifact in registration["artifacts"]:
    path=repo/"checkpoint"/artifact["filename"];path.parent.mkdir(parents=True,exist_ok=True)
    candidate=path if path.exists() else path.with_suffix(".partial")
    if not path.exists():urllib.request.urlretrieve(registration["weight_repository"]+"/resolve/"+registration["weight_revision"]+"/checkpoint/"+artifact["filename"],candidate)
    digest=hashlib.sha256()
    with candidate.open("rb") as handle:
        for chunk in iter(lambda:handle.read(1024*1024),b""):digest.update(chunk)
    if digest.hexdigest()!=artifact["sha256"]:raise ValueError("Checkpoint hash mismatch: "+artifact["filename"])
    if candidate!=path:candidate.replace(path)
    print(artifact["filename"]+" verified",flush=True)
lock=subprocess.check_output([python,"-m","pip","freeze"],text=True)
(root/"data/separation/tools/audiosep-environment-lock.txt").write_text(lock,encoding="utf-8")
print("Prepared. Existing service packages were reused read-only through .pth.")
