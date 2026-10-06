"""Brass listening candidates, without changing account analyses or production defaults."""
import argparse, os, time
from pathlib import Path
import numpy as np
import soundfile as sf
from music_analyzer.common import project_root, read_json, write_json, sha256_file

ROOT=project_root(); DATA=ROOT/'data/separation'; OUT=ROOT/'data/part-studies/brass-red-shoes'
RATE=44100
NEGATIVE='piano, electronic synthesizer, bowed strings, acoustic guitar, electric guitar, bass, drums and singing'

def prepare():
    row=read_json(DATA/'web/analysis_d02be493cd3444e8ad3d2c5a87f55659/record.json')
    paths={'original':row['original'],'instrumental':row['instrumental'],**{t['family']:t['path'] for t in row['tracks']}}
    for label in ('original','instrumental','other','synth','strings'):
        with sf.SoundFile(DATA/paths[label]) as f:
            assert f.samplerate==RATE and f.channels==2
            f.seek(24*RATE); audio=f.read(36*RATE,dtype='float32',always_2d=True)
        assert audio.shape==(36*RATE,2) and np.isfinite(audio).all()
        sf.write(OUT/(label+'.wav'),audio,RATE,subtype='FLOAT')
    orange=ROOT/'data/reset-backups/reset-20261006-193853/jobs/job_8597042ce35145d0a1d3885fc47956d4/result/stems/instrumental.wav'
    with sf.SoundFile(orange) as f:
        f.seek(9*RATE); audio=f.read(20*RATE,dtype='float32',always_2d=True)
    assert audio.shape==(20*RATE,2)
    sf.write(OUT/'orange-instrumental.wav',audio,RATE,subtype='FLOAT')
    write_json(OUT/'source.json',{'analysis_id':row['id'],'start_sec':24,'end_sec':60,
        'input_hashes':{name:sha256_file(OUT/(name+'.wav')) for name in ('original','instrumental','other','synth','strings','orange-instrumental')},
        'negative_control':'Orange 9–29s, user reported no brass','ground_truth':False})

def mega():
    import torch
    from filelock import FileLock
    from music_analyzer.mega53_experiment import configuration, prune_heads, CHECKPOINT_SHA, folder
    from music_analyzer.vendor.msst.bs_roformer import BSRoformer
    from music_analyzer.roformer_runner import overlap_infer
    checkpoint=folder()/'official-53.ckpt'
    assert sha256_file(checkpoint)==CHECKPOINT_SHA
    config=configuration();assert config['training']['instruments'][8]=='brass'
    config['model']['num_stems']=1
    with FileLock(str(DATA/'runtime/gpu-execution.lock'),timeout=0):
        torch.manual_seed(0); torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
        model=BSRoformer(**config['model'])
        model.load_state_dict(prune_heads(torch.load(checkpoint,map_location='cpu',weights_only=True),(8,)),strict=True)
        model.eval().cuda(); reports=[]
        for label in ('instrumental','other','orange-instrumental'):
            audio,rate=sf.read(OUT/(label+'.wav'),dtype='float32',always_2d=True)
            torch.cuda.reset_peak_memory_stats();started=time.perf_counter()
            def infer(piece):
                with torch.inference_mode(),torch.autocast('cuda',dtype=torch.float16):
                    return model(torch.from_numpy(piece)[None].cuda())[0].float().cpu().numpy()
            result=overlap_infer(audio.T,10*RATE,.5,infer,output_stems=1)[0].T
            assert result.shape==audio.shape and np.isfinite(result).all()
            sf.write(OUT/('mega-'+label+'.wav'),result,rate,subtype='FLOAT')
            if label=='other':sf.write(OUT/'after-mega.wav',audio-result,rate,subtype='FLOAT')
            reports.append({'input':label,'wall_sec':time.perf_counter()-started,'peak_allocated_bytes':torch.cuda.max_memory_allocated()})
            print(label,'BRASS READY',flush=True)
        write_json(OUT/'mega-benchmark.json',{'checkpoint_sha256':CHECKPOINT_SHA,'head':8,'reports':reports,'quality_verified':False})

def clap():
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
    from music_analyzer import part_study
    part_study.PROMPTS['brass_study']={'baseline':['brass instruments playing, trumpets, trombones and French horns',NEGATIVE],
        'a':['trumpets and trombones playing short brass hits',NEGATIVE],
        'b':['brass instruments playing sustained melodic notes',NEGATIVE],'labels':['brass_hits','brass_sustain']}
    cases=[]
    for label in ('instrumental','other','after-mega','orange-instrumental'):
        path=OUT/(label+'.wav')
        cases.append({'name':label,'family':'brass_study','input':str(path),'input_sha256':sha256_file(path),
                      'output':str(OUT/('clap-'+label)),'full_song_study':True})
    write_json(OUT/'plan.json',{'data_root':str(DATA),'cases':cases})
    part_study.infer_plan(OUT/'plan.json')

def build():
    import html
    candidates={'원곡':'original.wav','반주':'instrumental.wav','현재 나머지':'other.wav',
        '현재 신디':'synth.wav','현재 스트링':'strings.wav','Mega53 브라스 · 반주 입력':'mega-instrumental.wav',
        'Mega53 브라스 · 나머지 입력':'mega-other.wav'}
    mega,rate=sf.read(OUT/'mega-other.wav',dtype='float32',always_2d=True)
    other,_=sf.read(OUT/'other.wav',dtype='float32',always_2d=True)
    checks=[]
    for name,title in (('baseline','일반'),('part_a','짧은 연주'),('part_b','지속음')):
        candidates['CLAPSep '+title+' · 반주 입력']='clap-instrumental/'+name+'.wav'
        candidates['CLAPSep '+title+' · 나머지 입력']='clap-other/'+name+'.wav'
        recovery,_=sf.read(OUT/('clap-after-mega/'+name+'.wav'),dtype='float32',always_2d=True)
        combined=mega+recovery;remaining=other-combined
        assert combined.shape==other.shape and np.isfinite(combined).all()
        err=float(np.max(np.abs(combined.astype(np.float64)+remaining-other)))
        assert err<2e-7
        sf.write(OUT/('combined-'+name+'.wav'),combined,rate,subtype='FLOAT')
        sf.write(OUT/('remaining-'+name+'.wav'),remaining,rate,subtype='FLOAT')
        candidates['전용+보완 · '+title]='combined-'+name+'.wav'
        candidates['보완 후 나머지 · '+title]='remaining-'+name+'.wav'
        checks.append({'query':name,'pair_max_abs_error':err})
    candidates.update({'오렌지 · 반주':'orange-instrumental.wav','오렌지 · 전용 브라스':'mega-orange-instrumental.wav'})
    for name,title in (('baseline','일반'),('part_a','짧은 연주'),('part_b','지속음')):
        candidates['오렌지 · CLAPSep '+title]='clap-orange-instrumental/'+name+'.wav'
    preview=OUT/'preview';preview.mkdir(exist_ok=True);cards=[];metrics=[]
    for index,(title,path) in enumerate(candidates.items()):
        audio,rate=sf.read(OUT/path,dtype='float32',always_2d=True)
        assert rate==RATE and audio.shape[1]==2 and np.isfinite(audio).all()
        rms=float(np.sqrt(np.mean(audio.astype(np.float64)**2)));peak=float(np.max(np.abs(audio)))
        gain=min(4,.06/max(rms,1e-12),.9/max(peak,1e-12))
        sf.write(preview/(str(index)+'.wav'),audio*gain,rate,subtype='PCM_16')
        metrics.append({'title':title,'path':path,'rms':rms,'preview_gain':gain})
        cards.append(f'<section><h2>{html.escape(title)}</h2><audio controls preload="none" src="preview/{index}.wav"></audio><p>청취 음량 ×{gain:.2f} · <a href="{path}">원시 출력</a></p></section>')
    write_json(OUT/'verification.json',{'checks':checks,'metrics':metrics,'quality_verified':False,'account_library_changed':False})
    page='<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>분홍신 브라스 비교</title><style>body{background:#101620;color:#edf2fa;font:16px system-ui;max-width:1100px;margin:32px auto;padding:0 20px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px}section{background:#192638;padding:18px;border-radius:14px}h2{font-size:18px}audio{width:100%}p{color:#bac9dc;line-height:1.6}a{color:#b5a0ff}</style><h1>분홍신 · 브라스 24–60초</h1><p>원하는 브라스 연주와 기타·드럼·보컬 유입을 확인해주세요. 전용+보완 후보는 나머지에만 적용한 실험입니다. 신디·스트링으로 이미 분류된 브라스는 되찾지 못할 수 있습니다. 청취 음량은 최대 4배이며 정확도 판정은 아직 하지 않았습니다. 오렌지는 9–29초의 브라스 없는 비교 구간입니다.</p><main>'+''.join(cards)+'</main><script>document.querySelectorAll("audio").forEach(a=>a.addEventListener("play",()=>document.querySelectorAll("audio").forEach(b=>{if(a!==b)b.pause()})))</script></html>'
    (OUT/'comparison.html').write_text(page,encoding='utf-8')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=['prepare','mega','clap','build'])
    args=parser.parse_args();OUT.mkdir(parents=True,exist_ok=True);globals()[args.mode]()
