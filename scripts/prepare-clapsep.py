"""Prepare CLAPSep after scripts/prepare-audiosep.py; run with project .venv."""
import hashlib,json,subprocess,urllib.request,venv
from pathlib import Path
root=Path(__file__).resolve().parents[1]
r=json.loads((root/"separation/configs/models/clapsep.json").read_text(encoding="utf-8"))
repo=root/"data/separation/tools/CLAPSepInference";env=root/"data/separation/tools/clapsep-env"
base_env=root/"data/separation/tools/audiosep-env/Lib/site-packages"
if not base_env.exists():raise ValueError("Run scripts/prepare-audiosep.py first")
if not (env/"Scripts/python.exe").exists():venv.EnvBuilder(with_pip=True).create(env)
(env/"Lib/site-packages/music_analyzer_base.pth").write_text("\n".join(str(p) for p in (base_env,root/".venv/Lib/site-packages",root/"separation/src"))+"\n",encoding="utf-8")
python=str(env/"Scripts/python.exe")
subprocess.run([python,"-m","pip","install","laion-clap==1.1.7","loralib==0.1.2"],check=True)
items=list(r["code_hashes"].items())+[("model/"+a["filename"],a["sha256"]) for a in r["artifacts"]]
for name,digest in items:
    path=repo/name;path.parent.mkdir(parents=True,exist_ok=True)
    candidate=path if path.exists() else path.with_suffix(".partial")
    if not path.exists():urllib.request.urlretrieve(r["repository_url"]+"/resolve/"+r["revision"]+"/"+name,candidate)
    observed=hashlib.sha256()
    with candidate.open("rb") as handle:
        for chunk in iter(lambda:handle.read(1024*1024),b""):observed.update(chunk)
    if observed.hexdigest()!=digest:raise ValueError("Hash mismatch: "+name)
    if path!=candidate:candidate.replace(path)
    print(name+" verified",flush=True)
(root/"data/separation/tools/clapsep-environment-lock.txt").write_text(subprocess.check_output([python,"-m","pip","freeze"],text=True),encoding="utf-8")
print("CLAPSep prepared in isolated environment")
