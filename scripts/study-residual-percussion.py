"""Test percussion evidence after removing louder piano/guitar/bass/drums."""
import copy,time,argparse
from pathlib import Path
import numpy as np,soundfile as sf,torch
from filelock import FileLock,Timeout
from music_analyzer.common import project_root,read_json,write_json,sha256_file
from music_analyzer.mega53_experiment import configuration,prune_heads,CHECKPOINT_SHA,folder
from music_analyzer.vendor.msst.bs_roformer import BSRoformer
from music_analyzer.roformer_runner import overlap_infer
from music_analyzer.percussion_refinement import transfer
from music_analyzer.ground_truth import score

parser=argparse.ArgumentParser();parser.add_argument('--all',action='store_true');parser.add_argument('--drums-residual',action='store_true');args=parser.parse_args()
base=project_root();cases=base/'data/ground-truth/cases';study=cases/('drums-residual-percussion-study' if args.drums_residual else 'residual-percussion-study');study.mkdir(exist_ok=True)
selected=[32,40];config=copy.deepcopy(configuration());labels=[config['training']['instruments'][i] for i in selected];config['model']['num_stems']=2
checkpoint=folder()/'official-53.ckpt';assert sha256_file(checkpoint)==CHECKPOINT_SHA
weights=torch.load(checkpoint,map_location='cpu',weights_only=True);reduced=prune_heads(weights,selected);del weights
model=BSRoformer(**config['model']);model.load_state_dict(reduced,strict=True);del reduced
runtime=base/'data/separation/runtime';summary=[]
while True:
    lock=FileLock(str(runtime/'supervisor.lock'),timeout=0)
    try:lock.acquire();break
    except Timeout:time.sleep(1)
try:
    with FileLock(str(runtime/'gpu-execution.lock'),timeout=0):
        torch.manual_seed(0);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False;model.eval().cuda()
        for case in sorted(cases.iterdir()):
            if not (case/'run.json').exists() or not (case/'prepared.json').exists():continue
            if not args.all and case.name not in ['real-quiet-timpani','real-timpani','mallet-quiet-94-109','slakh20-pad-15-30','real-no-timpani']:continue
            prepared=read_json(case/'prepared.json')
            if prepared.get('exclude_from_evaluation'):continue
            latest=cases/'stability-v11'/case.name;execution=read_json((latest if (latest/'report.json').exists() else case)/'run.json');root=Path(execution['root']);row=read_json(root/'web'/execution['id']/'record.json')
            job=row['job_ids'][-1];manifest=read_json(root/'jobs'/job/'result/manifest.json')
            input_path=root/'inputs'/manifest['asset_id']/'canonical.wav';audio=sf.read(input_path,dtype='float32',always_2d=True)[0]
            tracks={t['family']:sf.read(root/t['path'],dtype='float32',always_2d=True)[0] for t in row['tracks']}
            if row.get('percussion_refinement'):
                for f,t in row['percussion_refinement']['original_tracks'].items():tracks[f]=sf.read(root/t['path'],dtype='float32',always_2d=True)[0]
            elif (case/'without-recovery/other.wav').exists():tracks['other']=sf.read(case/'without-recovery/other.wav',dtype='float32',always_2d=True)[0]
            if args.drums_residual:
                output=study/case.name;output.mkdir(exist_ok=True);input_path=output/'source.wav'
                audio=tracks['drums']+tracks['other'];sf.write(input_path,audio,44100,subtype='FLOAT')
            output=study/case.name;output.mkdir(exist_ok=True);proof=output/'proof.json';digest=sha256_file(input_path)
            if proof.exists() and read_json(proof)['input_sha256']==digest:
                estimates=[sf.read(output/(label+'.wav'),dtype='float32',always_2d=True)[0] for label in labels]
            else:
                print(case.name,'RESIDUAL INFERENCE',flush=True)
                def infer(piece):
                    with torch.inference_mode(),torch.autocast('cuda',dtype=torch.float16):return model(torch.from_numpy(piece).unsqueeze(0).cuda())[0].float().cpu().numpy()
                estimates=[a.T for a in overlap_infer(audio.T.copy(),441000,.4,infer,output_stems=2)]
                for label,a in zip(labels,estimates):sf.write(output/(label+'.wav'),a,44100,subtype='FLOAT')
                write_json(proof,{'input_sha256':digest,'source_analysis':row['id'],'source_job':job,'source_checkpoint_sha256':CHECKPOINT_SHA,'heads':selected})
            original=[sf.read(cases/'extended-head-study'/case.name/(label+'.wav'),dtype='float32',always_2d=True)[0] for label in labels]
            before_drums,_,before=transfer(tracks['drums'],tracks['other'],*original);d,o,after=transfer(tracks['drums'],tracks['other'],*original,*estimates)
            timpani_drums,_,timpani_only=transfer(tracks['drums'],tracks['other'],*original,estimates[1])
            ref=prepared['references'].get('pitched_percussion');target=sf.read(ref['path'],dtype='float32',always_2d=True)[0] if ref else np.zeros_like(audio);mix=sf.read(prepared['input'],dtype='float32',always_2d=True)[0]
            drum_ref=prepared['references'].get('drums');drum_target=sf.read(drum_ref['path'],dtype='float32',always_2d=True)[0] if drum_ref else np.zeros_like(mix)
            item={'case':case.name,'before':score(target,before,mix),'after':score(target,after,mix),
                  'timpani_only':score(target,timpani_only,mix),'drums_before':score(drum_target,before_drums,mix),
                  'drums_after':score(drum_target,d,mix),'drums_timpani_only':score(drum_target,timpani_drums,mix)};summary.append(item)
            print(case.name,item['before']['raw_sdr_db'],item['after']['raw_sdr_db'],item['before']['target_gain'],item['after']['target_gain'],item['after']['output_to_mix_db'],flush=True)
        write_json(base/'docs'/('DRUMS_RESIDUAL_PERCUSSION_RESULTS.json' if args.drums_residual else 'RESIDUAL_PERCUSSION_RESULTS.json'),summary)
finally:lock.release()
