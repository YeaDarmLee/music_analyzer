"""Run all 53 official Mega53 heads on the pad-eval mixes; store heads and per-head reference projections."""
import copy,time
import numpy as np,soundfile as sf,torch
from filelock import FileLock,Timeout
from music_analyzer.common import project_root,read_json,write_json,sha256_file
from music_analyzer.mega53_experiment import configuration,prune_heads,CHECKPOINT_SHA,folder as model_folder
from music_analyzer.vendor.msst.bs_roformer import BSRoformer
from music_analyzer.roformer_runner import overlap_infer

base=project_root();cases=base/'data/pad-eval/cases';out=base/'data/pad-eval/heads';out.mkdir(exist_ok=True)
config=configuration();labels=config['training']['instruments'];rows={}
checkpoint=model_folder()/'official-53.ckpt';assert sha256_file(checkpoint)==CHECKPOINT_SHA
weights=torch.load(checkpoint,map_location='cpu',weights_only=True);reduced=prune_heads(weights,tuple(range(53)));del weights
config=copy.deepcopy(config);config['model']['num_stems']=53
model=BSRoformer(**config['model']);model.load_state_dict(reduced,strict=True);del reduced
runtime=base/'data/separation/runtime'
while True:
    supervisor=FileLock(str(runtime/'supervisor.lock'),timeout=0)
    try:supervisor.acquire();break
    except Timeout:time.sleep(2)
try:
    with FileLock(str(runtime/'gpu-execution.lock'),timeout=0):
        torch.manual_seed(0);model.eval().cuda()
        for case in sorted(cases.iterdir()):
            k=read_json(case/'case.json')
            if k['kind']=='pad_piano_only':continue
            target=out/(case.name+'.npz')
            prepared=read_json(case/'prepared.json');audio=sf.read(prepared['input'],dtype='float32',always_2d=True)[0]
            if not target.exists():
                def infer(piece):
                    with torch.inference_mode(),torch.autocast('cuda',dtype=torch.float16):
                        return model(torch.from_numpy(piece).unsqueeze(0).cuda())[0].float().cpu().numpy()
                est=overlap_infer(audio.T.copy(),441000,.4,infer,output_stems=53)
                keep={labels[i]:e.T.astype(np.float16) for i,e in enumerate(est) if float(np.sqrt(np.mean(e**2)))>1e-3*float(np.sqrt(np.mean(audio**2)))}
                np.savez_compressed(target,**keep)
            heads=np.load(target);print(case.name,len(heads.files),flush=True)
finally:supervisor.release()
print('PAD HEADS DONE',flush=True)
