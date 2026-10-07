"""Reproducible reference-stem evaluation in an isolated WebLibrary."""
from __future__ import annotations

import argparse
import html
import math
import os
from pathlib import Path
import time
from urllib.parse import quote

import numpy as np
import soundfile as sf

from .audio import RATE, write_raw
from .common import project_root, read_json, write_json, sha256_file
from .evaluation import raw_sdr, si_sdr


def score(target, estimate, mixture):
    arrays = [np.asarray(a, dtype=np.float64) for a in (target, estimate, mixture)]
    if any(a.shape != arrays[0].shape or a.ndim != 2 or a.shape[1] != 2
           or not a.size or not np.isfinite(a).all() for a in arrays):
        raise ValueError('Expected matching finite stereo timelines')
    target, estimate, mixture = arrays
    energy = lambda a: float(np.sum(a * a))
    db = lambda numerator, denominator: float(10 * np.log10(max(numerator, 1e-24) / max(denominator, 1e-24)))
    target_energy, output_energy, mix_energy = map(energy, arrays)
    absent = target_energy == 0
    return {
        'reference_absent': absent,
        'reference_rms': float(np.sqrt(np.mean(target * target))),
        'output_rms': float(np.sqrt(np.mean(estimate * estimate))),
        'error_rms': float(np.sqrt(np.mean((target-estimate)**2))),
        'raw_sdr_db': raw_sdr(target, estimate),
        'si_sdr_db': si_sdr(target, estimate),
        'output_to_mix_db': db(output_energy, mix_energy) if mix_energy else None,
        'target_gain': None if absent else float(np.sum(target * estimate) / target_energy),
        'silence_output_dbfs': db(output_energy, estimate.size) if absent else None,
    }


def prepare(config_path):
    config = read_json(config_path)
    folder = config_path.parent
    seconds, start = config['duration_sec'], config['start_sec']
    if not 1 <= seconds <= 30 or start < 0:
        raise ValueError('Use 1–30 second evaluation clips')
    references = {}
    sources = []
    for family, paths in config['reference_sources'].items():
        audio = np.zeros((round(seconds*RATE), 2), dtype=np.float32)
        for name in paths:
            path = (folder/name).resolve()
            with sf.SoundFile(path) as handle:
                native_rate, channels = handle.samplerate, handle.channels
                if channels not in (1,2):
                    raise ValueError('Source must be mono or stereo')
                handle.seek(round(start*native_rate))
                part = handle.read(round(seconds*native_rate), dtype='float32', always_2d=True)
            if len(part) != round(seconds*native_rate):
                raise ValueError('Source does not cover the clip')
            if channels == 1:
                part = np.repeat(part,2,axis=1)
            if native_rate != RATE:
                from scipy.signal import resample_poly
                divisor = math.gcd(native_rate,RATE)
                part = resample_poly(part,RATE//divisor,native_rate//divisor,axis=0).astype(np.float32)
            if part.shape != audio.shape:
                raise ValueError('Source does not cover the clip')
            audio += part
            sources.append({'family': family, 'path': str(path), 'sha256': sha256_file(path),
                            'native_rate':native_rate,'native_channels':channels})
        gain = float(config.get('reference_gains',{}).get(family,1))
        if not math.isfinite(gain) or gain < 0:
            raise ValueError('Invalid reference gain')
        audio *= gain
        path = folder/'references'/(family+'.wav')
        write_raw(path, audio)
        references[family] = {'path': str(path.resolve()), 'sha256': sha256_file(path)}
    mixture = sum((sf.read(r['path'], dtype='float32', always_2d=True)[0]
                   for r in references.values()), np.zeros_like(audio))
    mix_path = folder/'mix.wav'
    write_raw(mix_path, mixture)
    write_json(folder/'prepared.json', {**config, 'references': references, 'sources': sources,
               'input': str(mix_path.resolve()), 'input_sha256': sha256_file(mix_path)})


def evaluate(folder, root, row):
    from .web_server import WebLibrary
    prepared = read_json(folder/'prepared.json')
    mixture, rate = sf.read(prepared['input'], dtype='float32', always_2d=True)
    if sha256_file(Path(prepared['input'])) != prepared['input_sha256']:
        raise ValueError('Evaluation mixture changed')
    library = WebLibrary(root)
    try:
        analyzed_mix, analyzed_rate = sf.read(library.track_path(row,'original'),dtype='float32',always_2d=True)
        if rate != RATE or analyzed_rate != RATE or not np.array_equal(mixture,analyzed_mix):
            raise ValueError('Prepared mixture differs from the audio actually analyzed')
        outputs = {t['family']: sf.read(library.track_path(row,t['family']), dtype='float32', always_2d=True)[0]
                   for t in row['tracks']}
        expected=13 if row.get('separation_version') in ('staged-context-percussion-v11','staged-context-percussion-v12','staged-context-strings-v13','staged-context-backing-v14','staged-context-families-v15','staged-context-pads-v16') else 12
        if len(outputs) != expected:
            raise ValueError('Expected all raw outputs, including hidden silent tracks')
        candidate = {name: audio.copy() for name,audio in outputs.items()}
        for family in ('synth','strings','brass'):
            recovery = row.get(family+'_recovery')
            if recovery:
                before = recovery['original_tracks'][family]
                candidate[family] = sf.read(library.safe(before['path']), dtype='float32', always_2d=True)[0]
                candidate['other'] += outputs[family]-candidate[family]
        for family,audio in candidate.items():
            write_raw(folder/'without-recovery'/(family+'.wav'),audio)
        candidate_partition_error = float(np.max(np.abs(sum(candidate.values())-sum(outputs.values()))))
        if candidate_partition_error > 2e-6:
            raise ValueError('Candidate changed the output sum')
        groups = {family: [family] for family in outputs}
        groups['guitar_total'] = [f for f in ('acoustic_guitar', 'guitar', 'guitar_residual') if f in outputs]
        # Residual has no independent instrument truth; evaluate its guitar parent jointly.
        groups.pop('guitar_residual',None)
        metrics = {}
        listening_rows = []
        peak = max(float(np.abs(a).max()) for a in [mixture,*outputs.values(),*candidate.values()])
        for family, members in groups.items():
            target = np.zeros_like(mixture)
            if family == 'guitar_total':
                reference_names = ['acoustic_guitar', 'guitar']
            else:
                reference_names = ['percussion','pitched_percussion'] if family=='percussion' else ['synth','synth_strings'] if family=='synth' else [family]
            for name in reference_names:
                reference = prepared['references'].get(name)
                if reference:
                    path = Path(reference['path'])
                    if sha256_file(path) != reference['sha256']:
                        raise ValueError('Evaluation reference changed')
                    target += sf.read(path, dtype='float32', always_2d=True)[0]
            estimate = sum((outputs[name] for name in members), np.zeros_like(mixture))
            reference_path = folder/'evaluation-references'/(family+'.wav')
            estimate_path = folder/'evaluation-outputs'/(family+'.wav')
            candidate_path = folder/'evaluation-candidates'/(family+'.wav')
            candidate_audio = sum((candidate[name] for name in members), np.zeros_like(mixture))
            for path,audio in ((reference_path,target),(estimate_path,estimate),(candidate_path,candidate_audio)):
                write_raw(path,audio)
                peak = max(peak,float(np.abs(audio).max()))
            players = ''.join('<td><audio controls preload="none" src="'+quote(os.path.relpath(path,folder).replace('\\','/'))+'"></audio></td>'
                              for path in (reference_path,estimate_path,candidate_path))
            listening_rows.append('<tr><th>'+html.escape(family)+'</th>'+players+'</tr>')
            metrics[family] = score(target, estimate, mixture)
            metrics[family]['without_recovery'] = score(target,candidate_audio,mixture)
            if np.any(target):
                metrics[family]['mixture_baseline'] = score(target,mixture,mixture)
            recovery = row.get(family+'_recovery')
            if recovery:
                before = recovery['original_tracks'][family]
                before_audio = sf.read(library.safe(before['path']), dtype='float32', always_2d=True)[0]
                metrics[family]['before_recovery'] = score(target,before_audio,mixture)
            metrics[family]['windows'] = [score(target[i:i+RATE], estimate[i:i+RATE], mixture[i:i+RATE])
                                         for i in range(0,len(mixture),RATE)]
        guitar_stage_scores = {}
        guitar_target = sf.read(folder/'evaluation-references/guitar_total.wav',dtype='float32',always_2d=True)[0]
        for index,identifier in enumerate(row['job_ids']):
            result_folder = root/'jobs'/identifier/'result'
            stems = read_json(result_folder/'manifest.json')['stems']
            families = {s['family'] for s in stems}
            if {'piano','guitar','bass','drums'}.issubset(families):
                stem = next(s for s in stems if s['family']=='guitar')
                guitar_stage_scores['base_guitar'] = score(guitar_target,sf.read(result_folder/stem['path'],dtype='float32',always_2d=True)[0],mixture)
            if identifier == row.get('tonal_job_id',row['job_ids'][-1]) and {'acoustic-guitar','electric-guitar','synth'}.issubset(families):
                discarded = sum((sf.read(result_folder/s['path'],dtype='float32',always_2d=True)[0]
                                 for s in stems if s['family'] in ('acoustic-guitar','electric-guitar')),np.zeros_like(mixture))
                guitar_stage_scores['discarded_residual_guitars'] = score(guitar_target,discarded,mixture)
        result = {'case': prepared['name'], 'analysis_id': row['id'], 'model': row['model'],
                  'separation_version': row['separation_version'], 'processing_seconds': row['processing_seconds'],
                  'has_bleed': prepared.get('has_bleed'), 'metrics': metrics,
                  'candidate_partition_max_abs_error': candidate_partition_error,
                  'guitar_stage_scores': guitar_stage_scores,
                  'provenance': {'prepared': str((folder/'prepared.json').resolve()),
                     'prepared_sha256': sha256_file(folder/'prepared.json'),
                     'preset_sha256': sha256_file(project_root()/'separation/configs/presets/demucs.json'),
                     'implementation_sha256': {name: sha256_file(Path(__file__).parent/name)
                         for name in ('web_server.py','synth_recovery.py','part_study.py','roformer_runner.py',
                                      'instrumental_restoration.py','percussion_refinement.py','piano_drum_refinement.py')},
                     'job_ids': row['job_ids']},
                  'outputs': {t['family']: str(library.track_path(row,t['family'])) for t in row['tracks']},
                  'sum_error_rms': float(np.sqrt(np.mean((sum(outputs.values())-mixture)**2)))}
        write_json(folder/'report.json', result)
        (folder/'comparison.html').write_text(
            '<!doctype html><meta charset="utf-8"><title>Reference comparison</title>'
            '<style>body{font:16px system-ui;max-width:1200px;margin:32px auto;padding:16px;background:#111;color:#eee}'
            'table{border-collapse:collapse}td,th{padding:10px;border-bottom:1px solid #444}audio{width:280px}</style>'
            '<h1>'+html.escape(prepared['name'])+f'</h1><p>정답 / 현재 {expected}트랙 / 보완 제거 후보. 모든 플레이어는 같은 고정 재생 음량입니다. 새 트랙을 재생하면 이전 트랙의 위치를 이어 듣습니다.</p>'
            '<p>입력 믹스 <audio controls src="mix.wav"></audio></p>'
            '<table><thead><tr><th>트랙</th><th>정답 stem</th><th>현재 결과</th><th>보완 제거 후보</th></tr></thead><tbody>'
            +''.join(listening_rows)+'</tbody></table><script>let previous;const players=[...document.querySelectorAll("audio")];'
            f'players.forEach(p=>{{p.volume={min(1,.9/max(peak,1))};'
            'p.addEventListener("play",()=>{if(previous&&previous!==p){const t=previous.currentTime;previous.pause();if(Number.isFinite(p.duration)&&t<p.duration)p.currentTime=t}previous=p})});</script>',encoding='utf-8')
        print(prepared['name'], 'REPORT', folder/'report.json', flush=True)
        for family, item in metrics.items():
            print(family, {key: item[key] for key in ('raw_sdr_db','output_to_mix_db','target_gain')}, flush=True)
        return result
    finally:
        library.executor.shutdown()


def run(folder):
    from .registry import paths
    from .web_server import WebLibrary
    prepared = read_json(folder/'prepared.json')
    root = folder/'library'
    for model_id in ('melband_roformer_kj','bs_roformer_6s','bs_karaoke','bs_roformer_mega5','bs_roformer_mega7'):
        checkpoint, registration = paths(project_root()/'data/separation',model_id)
        destination = root/'models'/model_id
        destination.mkdir(parents=True,exist_ok=True)
        if not (destination/checkpoint.name).exists():
            os.link(checkpoint,destination/checkpoint.name)
        write_json(destination/'registration.json',read_json(registration))
    library = WebLibrary(root)
    try:
        clip = Path(prepared['input'])
        if sha256_file(clip) != prepared['input_sha256']:
            raise ValueError('Evaluation mixture changed')
        with clip.open('rb') as stream:
            public = library.create(clip.name,'final_11',stream,clip.stat().st_size)
        write_json(folder/'run.json', {'id': public['id'], 'root': str(root.resolve())})
        started = time.monotonic()
        stage = None
        while True:
            row = library.get(public['id'])
            if row['stage'] != stage:
                stage = row['stage']; print(prepared['name'],stage,flush=True)
            if row['state'] in ('SUCCEEDED','FAILED','CANCELLED'):
                break
            if time.monotonic()-started > 1200:
                library.stopping.set()
                raise TimeoutError('Evaluation exceeded 20 minutes')
            time.sleep(.5)
        if row['state'] != 'SUCCEEDED':
            raise RuntimeError(row.get('error',row['state']))
    finally:
        library.executor.shutdown(wait=True)
    evaluate(folder,root,row)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare','run','evaluate'])
    parser.add_argument('path', type=Path)
    args = parser.parse_args()
    if args.action == 'prepare':
        prepare(args.path.resolve())
    elif args.action == 'run':
        run(args.path.resolve())
    else:
        folder = args.path.resolve()
        execution = read_json(folder/'run.json')
        root = Path(execution['root'])
        evaluate(folder,root,read_json(root/'web'/execution['id']/'record.json'))


if __name__ == '__main__':
    main()
