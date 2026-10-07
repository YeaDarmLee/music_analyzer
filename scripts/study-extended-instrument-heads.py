"""Inspect missing instrument families with official, independently pruned Mega53 heads."""
import copy
import time
import argparse
from pathlib import Path
import numpy as np
import soundfile as sf
import torch
from filelock import FileLock,Timeout
from music_analyzer.common import project_root,read_json,write_json,sha256_file
from music_analyzer.mega53_experiment import configuration,prune_heads,CHECKPOINT_SHA,folder as model_folder
from music_analyzer.vendor.msst.bs_roformer import BSRoformer
from music_analyzer.roformer_runner import overlap_infer
from music_analyzer.ground_truth import score

base=project_root();cases=base/'data/ground-truth/cases';study=cases/'extended-head-study'
parser=argparse.ArgumentParser();parser.add_argument('--missing-only',action='store_true');args=parser.parse_args()
study.mkdir(exist_ok=True)
selected=[6,7,8,12,17,19,25,29,31,32,37,38,40,51,52]
config=configuration();labels=config['training']['instruments']
targets={i:labels[i] for i in selected}
checkpoint=model_folder()/'official-53.ckpt'
assert sha256_file(checkpoint)==CHECKPOINT_SHA
weights=torch.load(checkpoint,map_location='cpu',weights_only=True)
reduced=prune_heads(weights,selected);del weights
config=copy.deepcopy(config);config['model']['num_stems']=len(selected)
model=BSRoformer(**config['model']);model.load_state_dict(reduced,strict=True);del reduced
runtime=base/'data/separation/runtime'
while True:
    supervisor=FileLock(str(runtime/'supervisor.lock'),timeout=0)
    try:supervisor.acquire();break
    except Timeout:time.sleep(2)
try:
    with FileLock(str(runtime/'gpu-execution.lock'),timeout=0):
        torch.manual_seed(0);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
        model.eval().cuda();summary=[]
        for case in sorted(cases.iterdir()):
            if not (case/'prepared.json').exists():continue
            prepared=read_json(case/'prepared.json')
            if prepared.get('exclude_from_evaluation'):continue
            audio=sf.read(prepared['input'],dtype='float32',always_2d=True)[0]
            output=study/case.name;output.mkdir(exist_ok=True)
            if args.missing_only and all((output/(label+'.wav')).exists() for label in targets.values()):continue
            if all((output/(label+'.wav')).exists() for label in targets.values()):
                estimates=[sf.read(output/(label+'.wav'),dtype='float32',always_2d=True)[0] for label in targets.values()]
            else:
                print(case.name,'EXTENDED INFERENCE',flush=True)
                def infer(piece):
                    with torch.inference_mode(),torch.autocast('cuda',dtype=torch.float16):
                        return model(torch.from_numpy(piece).unsqueeze(0).cuda())[0].float().cpu().numpy()
                estimates=overlap_infer(audio.T.copy(),441000,.4,infer,output_stems=len(selected))
                estimates=[estimate.T for estimate in estimates]
                for label,estimate in zip(targets.values(),estimates):sf.write(output/(label+'.wav'),estimate,44100,subtype='FLOAT')
            references={family:sf.read(item['path'],dtype='float32',always_2d=True)[0] for family,item in prepared['references'].items()}
            reference_names=list(references)
            basis=np.column_stack([references[name].reshape(-1)[::8] for name in reference_names])
            coefficients=np.linalg.lstsq(basis,np.column_stack([estimate.reshape(-1)[::8] for estimate in estimates]),rcond=None)[0]
            item={'case':case.name,'head_reference_coefficients':{label:dict(zip(reference_names,coefficients[:,i].tolist())) for i,label in enumerate(targets.values())},'scores':{}}
            for family,names in {'synth':['synth','keys','organ'],'strings':['bowed_strings','strings'],
                'brass':['brass'],'pitched_percussion':['bells','glockenspiel','marimba','timpani','wind-chimes']}.items():
                target=references.get(family,np.zeros_like(audio))
                group=sum(estimates[list(targets.values()).index(name)] for name in names)
                item['scores'][family]=score(target,group,audio)
            summary.append(item);write_json(study/'report.json',summary)
            print(case.name,{f:round(s['target_gain'],3) if s['target_gain'] is not None else round(s['output_to_mix_db'] or -999,1) for f,s in item['scores'].items()},flush=True)
        write_json(base/'docs/EXTENDED_INSTRUMENT_HEAD_RESULTS.json',{'source_checkpoint_sha256':CHECKPOINT_SHA,'heads':targets,'cases':summary})
finally:supervisor.release()
