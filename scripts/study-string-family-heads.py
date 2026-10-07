"""Probe individual orchestral string heads to separate synth pads from bowed strings."""
import copy,time
import numpy as np,soundfile as sf,torch
from filelock import FileLock,Timeout
from music_analyzer.common import project_root,read_json,write_json,sha256_file
from music_analyzer.mega53_experiment import configuration,prune_heads,CHECKPOINT_SHA,folder as model_folder
from music_analyzer.vendor.msst.bs_roformer import BSRoformer
from music_analyzer.roformer_runner import overlap_infer

base=project_root();cases=base/'data/ground-truth/cases';study=cases/'string-family-study';study.mkdir(exist_ok=True)
selected=[2,7,9,13,27,37,38,47,48,49]
config=configuration();labels=config['training']['instruments'];targets=[labels[i] for i in selected]
checkpoint=model_folder()/'official-53.ckpt';assert sha256_file(checkpoint)==CHECKPOINT_SHA
weights=torch.load(checkpoint,map_location='cpu',weights_only=True);reduced=prune_heads(weights,selected);del weights
config=copy.deepcopy(config);config['model']['num_stems']=len(selected)
model=BSRoformer(**config['model']);model.load_state_dict(reduced,strict=True);del reduced
runtime=base/'data/separation/runtime'
while True:
    supervisor=FileLock(str(runtime/'supervisor.lock'),timeout=0)
    try:supervisor.acquire();break
    except Timeout:time.sleep(2)
summary=[]
try:
    with FileLock(str(runtime/'gpu-execution.lock'),timeout=0):
        torch.manual_seed(0);model.eval().cuda()
        for case in sorted(cases.iterdir()):
            if not (case/'prepared.json').exists():continue
            prepared=read_json(case/'prepared.json')
            if prepared.get('exclude_from_evaluation'):continue
            output=study/case.name;output.mkdir(exist_ok=True)
            if not all((output/(t+'.wav')).exists() for t in targets):
                audio=sf.read(prepared['input'],dtype='float32',always_2d=True)[0]
                def infer(piece):
                    with torch.inference_mode(),torch.autocast('cuda',dtype=torch.float16):
                        return model(torch.from_numpy(piece).unsqueeze(0).cuda())[0].float().cpu().numpy()
                for t,e in zip(targets,overlap_infer(audio.T.copy(),441000,.4,infer,output_stems=len(selected))):
                    sf.write(output/(t+'.wav'),e.T,44100,subtype='FLOAT')
            refs={f:sf.read(r['path'],dtype='float32',always_2d=True)[0] for f,r in prepared['references'].items()}
            item={'case':case.name,'shares':{}}
            for t in targets:
                e=sf.read(output/(t+'.wav'),dtype='float32',always_2d=True)[0]
                item['shares'][t]={f:float((e*r).sum()/max((r*r).sum(),1e-12)) for f,r in refs.items() if (r*r).sum()>1e-9}
            summary.append(item);print(case.name,flush=True)
finally:supervisor.release()
write_json(study/'report.json',{'heads':targets,'checkpoint_sha256':CHECKPOINT_SHA,'cases':summary})
