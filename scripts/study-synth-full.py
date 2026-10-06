"""Full-song validation of the user-selected synth recovery, in an isolated library."""
import argparse
import os
import time
from pathlib import Path
import numpy as np
import soundfile as sf
from music_analyzer.common import project_root, read_json, write_json, sha256_file

ROOT = project_root()
DATA = ROOT / 'data/separation'
OUT = ROOT / 'data/part-studies/synth-full-validation'
POSITIVE = 'electronic synthesizer playing sustained chords'
NEGATIVE = 'electric guitar, acoustic guitar strumming, drums, lead singing and backing vocals'

def prepare():
    from music_analyzer.registry import paths
    from music_analyzer.web_server import WebLibrary
    library_root = OUT / 'orange-library'
    for model_id in ('melband_roformer_kj', 'bs_roformer_6s', 'bs_karaoke', 'bs_roformer_mega4'):
        checkpoint, registration = paths(DATA, model_id)
        folder = library_root / 'models' / model_id
        folder.mkdir(parents=True, exist_ok=True)
        if not (folder / checkpoint.name).exists():
            os.link(checkpoint, folder / checkpoint.name)
        write_json(folder / 'registration.json', read_json(registration))
    saved = OUT / 'sources.json'
    if saved.exists():
        return
    source = ROOT / 'data/reset-backups/reset-20261006-193853/inputs/asset_d8b1327923bd43c98a4cca041db58c25/canonical.wav'
    library = WebLibrary(library_root)
    try:
        with source.open('rb') as stream:
            row = library.create('orange.wav', 'final_10', stream, source.stat().st_size)
        previous = None
        while True:
            row = library.get(row['id'])
            if row['stage'] != previous:
                previous = row['stage']; print(previous, flush=True)
            if row['state'] in ('SUCCEEDED', 'FAILED', 'CANCELLED'):
                break
            time.sleep(1)
        assert row['state'] == 'SUCCEEDED', row.get('error')
        write_json(saved, {'miracle': {'root': str(DATA), 'record': str(DATA / 'web/analysis_27127556cdff41d3a68abdc248433838/record.json')},
                          'orange': {'root': str(library_root), 'record': str(library_root / 'web' / row['id'] / 'record.json')}})
    finally:
        library.executor.shutdown(wait=True)

def infer():
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    from music_analyzer import part_study
    part_study.PROMPTS['selected_synth'] = {
        'baseline': [POSITIVE, NEGATIVE], 'a': [POSITIVE, NEGATIVE],
        'b': [POSITIVE, NEGATIVE], 'labels': ['synth', 'synth']}
    cases = []
    for name, entry in read_json(OUT / 'sources.json').items():
        row = read_json(Path(entry['record']))
        track = next(t for t in row['tracks'] if t['family'] == 'other')
        path = Path(entry['root']) / track['path']
        cases.append({'name': name, 'family': 'selected_synth', 'input': str(path),
                      'input_sha256': sha256_file(path), 'output': str(OUT / name),
                      'full_song_study': True, 'queries': ['part_b']})
    write_json(OUT / 'plan.json', {'data_root': str(DATA), 'cases': cases})
    part_study.infer_plan(OUT / 'plan.json')

def build():
    import html
    sections, checks = [], []
    for name, entry in read_json(OUT / 'sources.json').items():
        row = read_json(Path(entry['record']))
        base = Path(entry['root'])
        tracks = {t['family']: t for t in row['tracks']}
        def read(path):
            audio, rate = sf.read(path, dtype='float32', always_2d=True)
            assert rate == 44100 and audio.ndim == 2 and audio.shape[1] == 2 and np.isfinite(audio).all()
            return audio
        original = read(base / row['original'])
        synth = read(base / tracks['synth']['path'])
        other = read(base / tracks['other']['path'])
        recovery = read(OUT / name / 'part_b.wav')
        assert original.shape == synth.shape == other.shape == recovery.shape
        revised_synth, revised_other = synth+recovery, other-recovery
        error = float(np.max(np.abs(synth.astype(np.float64)+other-revised_synth-revised_other)))
        assert error < 2e-7
        reconstructed = revised_synth.astype(np.float64)+revised_other
        for family, track in tracks.items():
            if family not in ('synth', 'other'):
                reconstructed += read(base / track['path'])
        full_error = float(np.max(np.abs(original-reconstructed)))
        assert full_error < 2e-6
        sf.write(OUT / name / 'synth-revised.wav', revised_synth, 44100, subtype='FLOAT')
        sf.write(OUT / name / 'other-revised.wav', revised_other, 44100, subtype='FLOAT')
        checks.append({'song': name, 'frames': len(original), 'pair_max_abs': error,
                       'ten_track_max_abs': full_error, 'quality_verified': False})
        preview = OUT / name / 'preview'; preview.mkdir(exist_ok=True)
        arrays = {'원곡': original, '기존 신디': synth, '보완 신디': revised_synth,
                  '기존 나머지': other, '보완 나머지': revised_other, '추가 추출분': recovery}
        # Identical gain for old/new pairs, no normalization that conceals changes.
        peaks = max(float(np.max(np.abs(a))) for a in arrays.values())
        gain = min(1., .9/max(peaks, 1e-12))
        cards = []
        for i, (label, audio) in enumerate(arrays.items()):
            sf.write(preview / f'{i}.wav', audio*gain, 44100, subtype='PCM_16')
            cards.append(f'<div><h3>{html.escape(label)}</h3><audio controls preload="none" src="{name}/preview/{i}.wav"></audio></div>')
        windows = [(14,24), (40,60), (100,120)] if name == 'miracle' else [(0,9), (9,20), (40,60), (100,120)]
        for start, end in windows:
            for label, audio in (('기존 신디', synth), ('보완 신디', revised_synth), ('추가 추출분', recovery)):
                index = len(cards)
                sf.write(preview / f'clip-{index}.wav', audio[start*44100:end*44100]*gain, 44100, subtype='PCM_16')
                cards.append(f'<div><h3>{start}–{end}초 · {label}</h3><audio controls preload="none" src="{name}/preview/clip-{index}.wav"></audio></div>')
        sections.append(f'<section><h2>{"미라클 제너레이션" if name=="miracle" else "오렌지"}</h2><div class="grid">'+''.join(cards)+'</div></section>')
    write_json(OUT / 'verification.json', {'checks': checks, 'account_library_changed': False})
    page = '<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>신디 보완 전체곡 비교</title><style>body{background:#101620;color:#edf2fa;font:16px system-ui;max-width:1100px;margin:32px auto;padding:0 20px}section{background:#192638;padding:20px;border-radius:14px;margin:24px 0}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:18px}audio{width:100%}h3{font-size:16px}p{line-height:1.6;color:#c0cede}</style><h1>신디사이저 보완 · 전체곡 비교</h1><p>선택한 지속 화음 추출을 전체 나머지에 적용했습니다. 기존·보완 출력은 같은 재생 음량입니다. 신디 연주가 유지되는지, 기타·드럼·보컬이 유입되는지 확인해주세요. 신디가 없는 구간이 있다면 잘못된 추출도 확인해주세요.</p>'+''.join(sections)+'<script>document.querySelectorAll("audio").forEach(a=>a.addEventListener("play",()=>document.querySelectorAll("audio").forEach(b=>{if(a!==b)b.pause()})))</script></html>'
    (OUT / 'comparison.html').write_text(page, encoding='utf-8')
    print('FULL SONG VALIDATION READY', flush=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['prepare', 'infer', 'build'])
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    globals()[args.mode]()
