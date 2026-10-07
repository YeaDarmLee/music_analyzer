"""Residual synth and strings recovery. Run inference in the pinned CLAPSep environment."""
from pathlib import Path
import argparse
import os
import numpy as np
import soundfile as sf
from .common import project_root, read_json, write_json, sha256_file

VERSION = 'clapsep-sustained-instrumental-v2'
POSITIVE = 'electronic synthesizer playing sustained chords'
NEGATIVE = 'piano, acoustic guitar strumming, electric guitar, bass and drums'

def settings(family):
    if family=='cymbal':return 'clapsep-harmonic-protected-cymbal-v1','ride cymbal being struck with drumsticks','piano playing melodic notes and chords','v1'
    if family=='synth':return VERSION,POSITIVE,NEGATIVE,'v2'
    if family=='strings':return 'clapsep-strings-brass-excluded-v2','bowed orchestral strings playing sustained chords','piano, electronic synthesizer, brass instruments, acoustic guitar strumming, electric guitar, bass and drums','v2'
    if family=='brass':return 'clapsep-brass-v1','brass instruments playing sustained chords','piano, electronic synthesizer, bowed orchestral strings, acoustic guitar strumming, electric guitar, bass and drums','v1'
    raise ValueError('Unsupported recovery family')

def infer(root, identifier, family='synth'):
    from . import part_study
    version,positive,negative,suffix=settings(family)
    root = Path(root).resolve()
    row = read_json(root/'web'/identifier/'record.json')
    track = next(t for t in row['tracks'] if t['family']==('piano' if family=='cymbal' else 'other'))
    source = (root/track['path']).resolve()
    if not source.is_relative_to(root): raise ValueError('Invalid source path')
    output = root/'web'/identifier/(family+'-recovery-'+suffix)
    part_study.PROMPTS['approved_synth'] = {
        'baseline':[positive,negative], 'a':[positive,negative],
        'b':[positive,negative], 'labels':[family,family]}
    plan = output/'plan.json'
    write_json(plan, {'data_root':str(project_root()/'data/separation'), 'cases':[
        {'name':identifier,'family':'approved_synth','input':str(source),
         'input_sha256':sha256_file(source),'output':str(output),
         'full_song_study':True,'queries':['part_b'],'report_progress':True}]})
    part_study.infer_plan(plan)

def apply(root, row, estimate, manifest, family='synth'):
    """Publish new files atomically, retaining original tracks and provenance for rollback."""
    if family=='cymbal':
        from .piano_drum_refinement import apply as apply_cymbal
        return apply_cymbal(root,row,estimate,manifest)
    root = Path(root).resolve()
    version,positive,negative,suffix=settings(family)
    selected_family=family
    if row.get(family+'_recovery',{}).get('version')==version: return row
    source = {t['family']:t for t in row['tracks']}
    meta = read_json(Path(manifest))
    if meta['case']['input_sha256'] != sha256_file(root/source['other']['path']):
        raise ValueError('Synth recovery input changed')
    result = meta['results']['part_b']
    if result['positive']!=positive or result['negative']!=negative or result['sha256']!=sha256_file(Path(estimate)):
        raise ValueError('Synth recovery provenance mismatch')
    arrays=[]
    for path in (root/source[selected_family]['path'],root/source['other']['path'],Path(estimate)):
        audio, rate=sf.read(path,dtype='float32',always_2d=True)
        if rate!=44100 or audio.shape[1]!=2 or not np.isfinite(audio).all(): raise ValueError('Invalid recovery audio')
        arrays.append(audio)
    synth, other, recovery=arrays
    if synth.shape!=other.shape or synth.shape!=recovery.shape: raise ValueError('Recovery timeline mismatch')
    revised={selected_family:synth+recovery,'other':other-recovery}
    error=float(np.max(np.abs(revised[selected_family].astype(np.float64)+revised['other']-synth.astype(np.float64)-other)))
    if error>2e-7: raise ValueError('Recovery reconstruction failed')
    instrumental_error=None
    if row.get('instrumental'):
        instrumental,rate=sf.read(root/row['instrumental'],dtype='float32',always_2d=True)
        if rate!=44100 or instrumental.shape!=synth.shape or not np.isfinite(instrumental).all():
            raise ValueError('Instrumental timeline mismatch')
        reconstructed=revised[selected_family].astype(np.float64)+revised['other']
        for family in ('piano','synth','strings','brass','acoustic_guitar','guitar','guitar_residual','bass','drums','percussion'):
            if family not in source:continue
            if family==selected_family:continue
            audio,rate=sf.read(root/source[family]['path'],dtype='float32',always_2d=True)
            if rate!=44100 or audio.shape!=synth.shape or not np.isfinite(audio).all():
                raise ValueError('Instrument timeline mismatch')
            reconstructed+=audio
        instrumental_error=float(np.max(np.abs(reconstructed-instrumental)))
        if instrumental_error>2e-6:raise ValueError('Instrumental reconstruction failed')
    folder=root/'web'/row['id']
    backup=folder/('record-before-'+selected_family+'-recovery-'+suffix+'.json')
    if not backup.exists(): write_json(backup,row)
    tracks=[]
    for track in row['tracks']:
        family=track['family']
        if family in revised:
            audio=revised[family]
            target=folder/(family+'-'+selected_family+'-recovered-'+suffix+'.wav')
            temporary=target.with_suffix('.partial.wav')
            sf.write(temporary,audio,44100,subtype='FLOAT');temporary.replace(target)
            peak=float(np.max(np.abs(audio)))
            track={k:v for k,v in track.items() if k not in ('silent','signal_rms')}
            track={**track,'path':str(target.relative_to(root)),'sha256':sha256_file(target),
                'peak':peak,'over_full_scale':peak>1,'derivation':'model_estimate_with_residual_'+selected_family+'_recovery'}
        tracks.append(track)
    return {**row,'tracks':tracks,selected_family+'_recovery':{'version':version,'positive':positive,
        'negative':negative,'manifest':str(Path(manifest).resolve()),'pair_max_abs_error':error,
        'instrumental_max_abs_error':instrumental_error,
        'original_tracks':{f:source[f] for f in (selected_family,'other')}}}

def run_for_library(library,row,family='synth',on_progress=None):
    import subprocess
    import time
    version,positive,negative,suffix=settings(family)
    if row.get(family+'_recovery',{}).get('version')==version:return row
    folder=library.web/row['id']
    write_json(folder/'record.json',row)
    python=project_root()/'data/separation/tools/clapsep-env/Scripts/python.exe'
    if not python.is_file():raise ValueError('악기 보완 모델 실행 환경이 없습니다.')
    env=os.environ.copy()
    cache=project_root()/'data/part-studies/clapsep-numba-cache'
    cache.mkdir(parents=True,exist_ok=True)
    env.update(PYTHONPATH=str(project_root()/'separation/src'),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',NUMBA_CACHE_DIR=str(cache))
    output=folder/(family+'-recovery-'+suffix)
    progress_path=output/'progress.json'
    progress_path.unlink(missing_ok=True)
    while not library.stopping.is_set():
        with (folder/(family+'-recovery.log')).open('w',encoding='utf-8') as log:
            process=subprocess.Popen([str(python),'-m','music_analyzer.synth_recovery','--root',str(library.root),'--id',row['id'],'--family',family],
                env=env,stdout=log,stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            started=time.monotonic();previous=None
            try:
                while process.poll() is None:
                    if library.stopping.is_set() or time.monotonic()-started>300:
                        raise ValueError('악기 보완 실행이 중단되거나 제한 시간을 초과했습니다.')
                    if on_progress and progress_path.exists():
                        progress=read_json(progress_path)
                        if progress!=previous:on_progress(progress);previous=progress
                    library.stopping.wait(.2)
            finally:
                if process.poll() is None:process.terminate();process.wait(timeout=10)
        if process.returncode==75:
            library.stopping.wait(1);continue
        if process.returncode:raise ValueError('악기 보완 추출 실패: '+str(folder/(family+'-recovery.log')))
        return apply(library.root,row,output/'part_b.wav',output/'manifest.json',family)
    raise ValueError('서버 종료로 악기 보완이 중단됐습니다.')

def main():
    from filelock import Timeout
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--id',required=True)
    parser.add_argument('--family',choices=['synth','strings','brass','cymbal'],default='synth')
    args=parser.parse_args()
    import re
    if not re.fullmatch(r'analysis_[0-9a-f]{32}',args.id):raise ValueError('Invalid analysis ID')
    try:infer(args.root,args.id,args.family)
    except Timeout:raise SystemExit(75)

if __name__=='__main__':main()
