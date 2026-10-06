"""Isolated synth candidates; never changes the account library or model defaults."""
import argparse
import time
from pathlib import Path
import numpy as np
import soundfile as sf
from music_analyzer.common import read_json, write_json, sha256_file, project_root

ROOT = project_root()
OUT = ROOT / 'data/part-studies/miracle-synth-check'
DATA = ROOT / 'data/separation'
RATE = 44100

def prepare():
    row = read_json(DATA / 'web/analysis_27127556cdff41d3a68abdc248433838/record.json')
    sources = {'original': row['original'], **{t['family']: t['path'] for t in row['tracks']}}
    for label in ('original', 'synth', 'other', 'piano'):
        with sf.SoundFile(DATA / sources[label]) as f:
            assert f.samplerate == RATE and f.channels == 2
            f.seek(14 * RATE)
            audio = f.read(10 * RATE, dtype='float32', always_2d=True)
        assert audio.shape == (10 * RATE, 2) and np.isfinite(audio).all()
        sf.write(OUT / f'{label}-14-24.wav', audio, RATE, subtype='FLOAT')
    orange = ROOT / 'data/part-studies/mega53-extended/orange'
    for label in ('original', 'synth'):
        path = (ROOT / 'data/part-studies/guitar-strings-orange/original.wav') if label == 'original' else orange / 'synth.wav'
        with sf.SoundFile(path) as f:
            f.seek(9 * RATE)
            audio = f.read(10 * RATE, dtype='float32', always_2d=True)
        assert audio.shape == (10*RATE,2) and np.isfinite(audio).all()
        sf.write(OUT / f'orange-{label}-9-19.wav', audio, RATE, subtype='FLOAT')
    cases = [{'name': label, 'family': 'synth_recovery',
              'input': str(OUT / f'{label}-14-24.wav'),
              'input_sha256': sha256_file(OUT / f'{label}-14-24.wav'),
              'output': str(OUT / f'clap-{label}')} for label in ('original', 'other')]
    write_json(OUT / 'plan.json', {'data_root': str(DATA), 'cases': cases})

def mega():
    import torch
    from filelock import FileLock
    from music_analyzer.mega53_experiment import configuration, prune_heads, CHECKPOINT_SHA, folder
    from music_analyzer.vendor.msst.bs_roformer import BSRoformer
    from music_analyzer.roformer_runner import overlap_infer
    selected = {25: 'keys', 38: 'synth'}
    weights_path = folder() / 'official-53.ckpt'
    assert sha256_file(weights_path) == CHECKPOINT_SHA
    config = configuration()
    assert all(config['training']['instruments'][i] == name for i, name in selected.items())
    with FileLock(str(DATA / 'runtime/gpu-execution.lock'), timeout=0):
        torch.manual_seed(0)
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        config['model']['num_stems'] = len(selected)
        model = BSRoformer(**config['model'])
        model.load_state_dict(prune_heads(torch.load(weights_path, map_location='cpu', weights_only=True), tuple(selected)), strict=True)
        model.eval().cuda()
        reports = []
        for label, path in (('original', 'original-14-24.wav'), ('other', 'other-14-24.wav'), ('orange', 'orange-original-9-19.wav')):
            audio, rate = sf.read(OUT / path, dtype='float32', always_2d=True)
            torch.cuda.reset_peak_memory_stats()
            started = time.perf_counter()
            def infer(piece):
                with torch.inference_mode(), torch.autocast('cuda', dtype=torch.float16):
                    return model(torch.from_numpy(piece)[None].cuda())[0].float().cpu().numpy()
            estimates = overlap_infer(audio.T, 10 * RATE, .5, infer, output_stems=2)
            torch.cuda.synchronize()
            reports.append({'input': label, 'inference_sec': time.perf_counter()-started,
                            'peak_allocated_bytes': torch.cuda.max_memory_allocated()})
            for name, estimate in zip(selected.values(), estimates, strict=True):
                assert estimate.shape == audio.T.shape and np.isfinite(estimate).all()
                sf.write(OUT / f'mega-{label}-{name}.wav', estimate.T, rate, subtype='FLOAT')
            print(label, 'MEGA READY', flush=True)
        write_json(OUT / 'mega-benchmark.json', {'heads': selected, 'checkpoint_sha256': CHECKPOINT_SHA,
                   'chunk_sec': 10, 'overlap': .5, 'reports': reports, 'quality_verified': False})

def clap():
    import os
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    from music_analyzer import part_study
    part_study.PROMPTS['synth_recovery'] = {
        'baseline': ['synthesizer', 'piano, electric guitar, drums, bass and singing'],
        'a': ['electronic synthesizer playing a bright melodic line', 'acoustic piano and electric guitar'],
        'b': ['electronic synthesizer playing sustained chords', 'acoustic piano and orchestral strings'],
        'labels': ['synth_melody', 'synth_chords']}
    part_study.infer_plan(OUT / 'plan.json')

def suppress():
    """Listening experiment: attenuate locally coherent leakage, never classify by energy alone."""
    from scipy.signal import stft, istft
    from scipy.ndimage import uniform_filter1d
    row = read_json(DATA / 'web/analysis_27127556cdff41d3a68abdc248433838/record.json')
    recovery, _ = sf.read(OUT / 'mega-other-synth.wav', dtype='float32', always_2d=True)
    def transform(audio):
        return stft(audio.T, fs=RATE, nperseg=2048, noverlap=1536)[2]
    candidate = transform(recovery)
    power = uniform_filter1d(np.abs(candidate)**2, 9, axis=-1)
    overlap = np.zeros(candidate.shape[1:], dtype=np.float64)
    references = []
    for track in row['tracks']:
        if track['family'] in ('synth', 'other'):
            continue
        with sf.SoundFile(DATA / track['path']) as f:
            f.seek(14*RATE)
            audio = f.read(10*RATE, dtype='float32', always_2d=True)
        assert audio.shape == recovery.shape and np.isfinite(audio).all()
        reference = transform(audio)
        cross = candidate * reference.conj()
        cross = uniform_filter1d(cross.real, 9, axis=-1) + 1j*uniform_filter1d(cross.imag, 9, axis=-1)
        ref_power = uniform_filter1d(np.abs(reference)**2, 9, axis=-1)
        coherence = np.clip(np.abs(cross)**2 / np.maximum(power*ref_power, 1e-16), 0, 1)
        # Ignore effectively silent references. Share one mask across channels to retain spatial ratios.
        coherence *= ref_power > 1e-10
        overlap = np.maximum(overlap, coherence.mean(axis=0))
        references.append(track['family'])
    overlap = uniform_filter1d(overlap, 3, axis=-1)
    for label, strength in (('mild', .5), ('strong', .85)):
        mask = 1-strength*overlap
        _, filtered = istft(candidate*mask[None], fs=RATE, nperseg=2048, noverlap=1536)
        filtered = filtered.T[:len(recovery)].astype(np.float32)
        assert filtered.shape == recovery.shape and np.isfinite(filtered).all()
        sf.write(OUT / f'filtered-{label}.wav', filtered, RATE, subtype='FLOAT')
    # Prove zero suppression reconstructs the input through the same transform.
    _, identity = istft(candidate, fs=RATE, nperseg=2048, noverlap=1536)
    error = float(np.max(np.abs(identity.T[:len(recovery)]-recovery)))
    assert error < 2e-7
    write_json(OUT / 'suppression-check.json', {'identity_max_abs_error': error,
        'references': references, 'shared_stereo_mask': True, 'quality_verified': False,
        'limitation': 'Correlated synth harmonics can be attenuated too; listening required.'})

def exclude():
    import os
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    from music_analyzer import part_study
    negative = 'electric guitar, acoustic guitar strumming, drums, lead singing and backing vocals'
    part_study.PROMPTS['synth_exclude'] = {
        'baseline': ['electronic synthesizer', negative],
        'a': ['electronic synthesizer playing a bright melodic line', negative],
        'b': ['electronic synthesizer playing sustained chords', negative],
        'labels': ['synth_melody', 'synth_chords']}
    plan = read_json(OUT / 'plan.json')
    for case in plan['cases']:
        case['family'] = 'synth_exclude'
        case['output'] = str(OUT / f"exclude-{case['name']}")
    write_json(OUT / 'exclude-plan.json', plan)
    part_study.infer_plan(OUT / 'exclude-plan.json')

def build():
    import html
    current, _ = sf.read(OUT / 'synth-14-24.wav', dtype='float32', always_2d=True)
    remaining, _ = sf.read(OUT / 'other-14-24.wav', dtype='float32', always_2d=True)
    recovery, _ = sf.read(OUT / 'mega-other-synth.wav', dtype='float32', always_2d=True)
    revised = current + recovery
    revised_remaining = remaining - recovery
    error = float(np.max(np.abs(current.astype(np.float64)+remaining-revised-revised_remaining)))
    assert error < 2e-7
    sf.write(OUT / 'candidate-synth.wav', revised, RATE, subtype='FLOAT')
    sf.write(OUT / 'candidate-other.wav', revised_remaining, RATE, subtype='FLOAT')
    write_json(OUT / 'reconstruction-check.json', {'max_abs_error': error, 'frames': len(current),
        'formula': 'candidate_synth=current_synth+recovery; candidate_other=current_other-recovery',
        'quality_verified': False, 'account_library_changed': False})
    candidates = {'원곡': 'original-14-24.wav', '현재 신디사이저': 'synth-14-24.wav',
                  '현재 나머지': 'other-14-24.wav', '현재 피아노': 'piano-14-24.wav',
                  '보완 후보 신디사이저': 'candidate-synth.wav', '보완 후보 나머지': 'candidate-other.wav'}
    for source, title in (('other', '나머지'), ('original', '원곡')):
        for name, description in (('baseline', '일반 신디'), ('part_a', '멜로디'), ('part_b', '지속 화음')):
            path = f'exclude-{source}/{name}.wav'
            if (OUT / path).exists():
                candidates[f'기타·드럼·보컬 제외 · {description} · {title} 입력'] = path
                if source == 'other':
                    estimate, _ = sf.read(OUT / path, dtype='float32', always_2d=True)
                    assert estimate.shape == current.shape and np.isfinite(estimate).all()
                    sf.write(OUT / f'exclude-synth-{name}.wav', current+estimate, RATE, subtype='FLOAT')
                    sf.write(OUT / f'exclude-other-{name}.wav', remaining-estimate, RATE, subtype='FLOAT')
                    np.testing.assert_allclose((current+estimate).astype(np.float64)+(remaining-estimate),
                        current.astype(np.float64)+remaining, atol=2e-7, rtol=0)
                    candidates[f'제외 조건 적용 후 나머지 · {description}'] = f'exclude-other-{name}.wav'
    for label, title in (('mild', '약하게'), ('strong', '강하게')):
        path = OUT / f'filtered-{label}.wav'
        if path.exists():
            filtered, _ = sf.read(path, dtype='float32', always_2d=True)
            sf.write(OUT / f'clean-synth-{label}.wav', current+filtered, RATE, subtype='FLOAT')
            sf.write(OUT / f'clean-other-{label}.wav', remaining-filtered, RATE, subtype='FLOAT')
            np.testing.assert_allclose((current+filtered).astype(np.float64)+(remaining-filtered),
                                       current.astype(np.float64)+remaining, atol=2e-7, rtol=0)
            candidates[f'다른 악기 억제 · {title} · 신디'] = f'clean-synth-{label}.wav'
            candidates[f'다른 악기 억제 · {title} · 나머지'] = f'clean-other-{label}.wav'
    for source, title in (('original', '원곡'), ('other', '나머지')):
        for head in ('keys', 'synth'):
            candidates[f'Mega53 {head} · {title} 입력'] = f'mega-{source}-{head}.wav'
        for name, description in (('baseline', '일반 신디'), ('part_a', '멜로디'), ('part_b', '지속 화음')):
            candidates[f'CLAPSep {description} · {title} 입력'] = f'clap-{source}/{name}.wav'
    candidates.update({'오렌지 9–19초 원곡': 'orange-original-9-19.wav',
                       '오렌지 기존 신디': 'orange-synth-9-19.wav',
                       '오렌지 keys 후보': 'mega-orange-keys.wav',
                       '오렌지 synth 후보': 'mega-orange-synth.wav'})
    preview = OUT / 'preview'
    preview.mkdir(exist_ok=True)
    cards, metrics = [], []
    for index, (title, path) in enumerate(candidates.items()):
        audio, rate = sf.read(OUT / path, dtype='float32', always_2d=True)
        assert rate == RATE and audio.shape == (10*RATE, 2) and np.isfinite(audio).all()
        rms = float(np.sqrt(np.mean(audio.astype(np.float64)**2)))
        peak = float(np.max(np.abs(audio)))
        gain = min(4., .06/max(rms, 1e-12), .9/max(peak, 1e-12))
        sf.write(preview / f'{index}.wav', audio*gain, RATE, subtype='PCM_16')
        metrics.append({'title': title, 'path': path, 'rms': rms, 'peak': peak, 'preview_gain': gain})
        cards.append(f'<section><h2>{html.escape(title)}</h2><audio controls preload="none" src="preview/{index}.wav"></audio><p>청취 음량 ×{gain:.2f} · <a href="{path}">원시 출력</a></p></section>')
    write_json(OUT / 'candidate-metrics.json', {'window': [14,24], 'tracks': metrics,
        'accuracy_score': None, 'quality_verified': False,
        'note': 'Output energy does not establish source identity. Independent candidates must not be summed.'})
    page = '<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>미라클 신디사이저 비교</title><style>body{background:#101620;color:#edf2fa;font:16px system-ui;max-width:960px;margin:32px auto;padding:0 20px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}section{background:#192638;border-radius:14px;padding:18px}h2{font-size:18px}audio{width:100%}p{line-height:1.6;color:#c0cede}a{color:#b5a0ff}</style><h1>미라클 제너레이션 · 14–24초</h1><p>해당 신디 연주가 들리는지, 피아노·기타가 따라오는지 비교해주세요. 청취 음량은 최대 4배로 조정했습니다. 원시 출력은 보존했으며 후보끼리 합산하지 않습니다.</p><main>' + ''.join(cards) + '</main><script>document.querySelectorAll("audio").forEach(a=>a.addEventListener("play",()=>document.querySelectorAll("audio").forEach(b=>{if(a!==b)b.pause()})))</script></html>'
    (OUT / 'comparison.html').write_text(page, encoding='utf-8')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['prepare', 'mega', 'clap', 'suppress', 'exclude', 'build'])
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    globals()[args.mode]()
