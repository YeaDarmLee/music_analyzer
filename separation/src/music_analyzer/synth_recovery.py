"""User-approved residual synth recovery. Run inference in the pinned CLAPSep environment."""
from pathlib import Path
import argparse
import os
import numpy as np
import soundfile as sf
from .common import project_root, read_json, write_json, sha256_file

VERSION = 'clapsep-sustained-v1'
POSITIVE = 'electronic synthesizer playing sustained chords'
NEGATIVE = 'electric guitar, acoustic guitar strumming, drums, lead singing and backing vocals'

def infer(root, identifier):
    from . import part_study
    root = Path(root).resolve()
    row = read_json(root/'web'/identifier/'record.json')
    track = next(t for t in row['tracks'] if t['family']=='other')
    source = (root/track['path']).resolve()
    if not source.is_relative_to(root): raise ValueError('Invalid source path')
    output = root/'web'/identifier/'synth-recovery-v1'
    part_study.PROMPTS['approved_synth'] = {
        'baseline':[POSITIVE,NEGATIVE], 'a':[POSITIVE,NEGATIVE],
        'b':[POSITIVE,NEGATIVE], 'labels':['synth','synth']}
    plan = output/'plan.json'
    write_json(plan, {'data_root':str(project_root()/'data/separation'), 'cases':[
        {'name':identifier,'family':'approved_synth','input':str(source),
         'input_sha256':sha256_file(source),'output':str(output),
         'full_song_study':True,'queries':['part_b']}]})
    part_study.infer_plan(plan)

def apply(root, row, estimate, manifest):
    """Publish new files atomically, retaining original tracks and provenance for rollback."""
    root = Path(root).resolve()
    if row.get('synth_recovery',{}).get('version')==VERSION: return row
    source = {t['family']:t for t in row['tracks']}
    meta = read_json(Path(manifest))
    if meta['case']['input_sha256'] != sha256_file(root/source['other']['path']):
        raise ValueError('Synth recovery input changed')
    result = meta['results']['part_b']
    if result['positive']!=POSITIVE or result['negative']!=NEGATIVE or result['sha256']!=sha256_file(Path(estimate)):
        raise ValueError('Synth recovery provenance mismatch')
    arrays=[]
    for path in (root/source['synth']['path'],root/source['other']['path'],Path(estimate)):
        audio, rate=sf.read(path,dtype='float32',always_2d=True)
        if rate!=44100 or audio.shape[1]!=2 or not np.isfinite(audio).all(): raise ValueError('Invalid recovery audio')
        arrays.append(audio)
    synth, other, recovery=arrays
    if synth.shape!=other.shape or synth.shape!=recovery.shape: raise ValueError('Recovery timeline mismatch')
    revised={'synth':synth+recovery,'other':other-recovery}
    error=float(np.max(np.abs(revised['synth'].astype(np.float64)+revised['other']-synth.astype(np.float64)-other)))
    if error>2e-7: raise ValueError('Recovery reconstruction failed')
    folder=root/'web'/row['id']
    backup=folder/'record-before-synth-recovery-v1.json'
    if not backup.exists(): write_json(backup,row)
    tracks=[]
    for track in row['tracks']:
        family=track['family']
        if family in revised:
            audio=revised[family]
            target=folder/(family+'-recovered-v1.wav')
            temporary=target.with_suffix('.partial.wav')
            sf.write(temporary,audio,44100,subtype='FLOAT');temporary.replace(target)
            peak=float(np.max(np.abs(audio)))
            track={**track,'path':str(target.relative_to(root)),'sha256':sha256_file(target),
                'peak':peak,'over_full_scale':peak>1,'derivation':'model_estimate_with_residual_synth_recovery'}
        tracks.append(track)
    return {**row,'tracks':tracks,'synth_recovery':{'version':VERSION,'positive':POSITIVE,
        'negative':NEGATIVE,'manifest':str(Path(manifest).resolve()),'pair_max_abs_error':error,
        'original_tracks':{f:source[f] for f in ('synth','other')}}}

def run_for_library(library,row):
    import subprocess
    if row.get('synth_recovery',{}).get('version')==VERSION:return row
    folder=library.web/row['id']
    write_json(folder/'record.json',row)
    python=project_root()/'data/separation/tools/clapsep-env/Scripts/python.exe'
    if not python.is_file():raise ValueError('신디사이저 보완 모델 실행 환경이 없습니다.')
    env=os.environ.copy()
    env.update(PYTHONPATH=str(project_root()/'separation/src'),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
    while not library.stopping.is_set():
        with (folder/'synth-recovery.log').open('w',encoding='utf-8') as log:
            result=subprocess.run([str(python),'-m','music_analyzer.synth_recovery','--root',str(library.root),'--id',row['id']],
                env=env,stdout=log,stderr=subprocess.STDOUT,timeout=300,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode==75:
            library.stopping.wait(1);continue
        if result.returncode:raise ValueError('신디사이저 보완 추출 실패: '+str(folder/'synth-recovery.log'))
        output=folder/'synth-recovery-v1'
        return apply(library.root,row,output/'part_b.wav',output/'manifest.json')
    raise ValueError('서버 종료로 신디사이저 보완이 중단됐습니다.')

def main():
    from filelock import Timeout
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--id',required=True)
    args=parser.parse_args()
    import re
    if not re.fullmatch(r'analysis_[0-9a-f]{32}',args.id):raise ValueError('Invalid analysis ID')
    try:infer(args.root,args.id)
    except Timeout:raise SystemExit(75)

if __name__=='__main__':main()
