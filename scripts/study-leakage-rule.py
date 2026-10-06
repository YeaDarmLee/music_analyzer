"""Offline energy baseline; thresholds are listening candidates, not presence truth."""
import html
import json
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/separation'
SOURCE = ROOT / 'data/part-studies/instrument-leakage-diagnosis/report.json'
OUT = ROOT / 'data/part-studies/instrument-leakage-rule'
RATE = 44100


def read(path, start, count):
    with sf.SoundFile(path) as f:
        assert f.samplerate == RATE and f.channels == 2
        f.seek(start)
        result = f.read(count, dtype='float32', always_2d=True)
    assert len(result) == count and np.isfinite(result).all()
    return result


def envelope(raw, mix, on, off, hold):
    """100 ms energy evidence, hysteresis, 50 ms attack and 300 ms release."""
    hop = RATE // 10
    levels, states = [], []
    active, remaining = False, 0
    for start in range(0, len(raw), hop):
        a, b = raw[start:start+hop], mix[start:start+hop]
        energy = float(np.sqrt(np.mean(a.astype(np.float64)**2)))
        reference = float(np.sqrt(np.mean(b.astype(np.float64)**2)))
        relative = 20*np.log10((energy+1e-12)/(reference+1e-12))
        if energy < 1e-5:
            active = False
        elif relative >= on:
            active, remaining = True, hold
        elif active and relative < off:
            remaining -= .1
            if remaining <= 0:
                active = False
        levels.append(relative)
        states.append(float(active))
    gain = np.empty(len(raw), dtype=np.float64)
    previous = 0.
    for index, state in enumerate(states):
        start, end = index*hop, min(len(raw), (index+1)*hop)
        tau = .05 if state > previous else .3
        decay = np.exp(-np.arange(1, end-start+1)/(RATE*tau))
        gain[start:end] = state + (previous-state)*decay
        previous = gain[end-1]
    return gain[:, None], levels


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    reports, cards = [], []
    for report in json.loads(SOURCE.read_text(encoding='utf-8')):
        name = report['name']
        if report['analysis_id'] != 'analysis_8842c174a4464e628994f81f911d1dca' and 'Malguem' not in name and '맑음' not in name:
            continue
        identifier, family = report['analysis_id'], report['family']
        row = json.loads((DATA/'web'/identifier/'record.json').read_text(encoding='utf-8'))
        tracks = {t['family']: t for t in row['tracks']}
        # Include preceding context so a preview does not start with a cold gate.
        preview_start = round(report['preview_start_sec']*RATE)
        context_start = max(0, preview_start-2*RATE)
        end = round(report['preview_end_sec']*RATE)
        count, offset = end-context_start, preview_start-context_start
        raw = read(report['raw_path'], context_start, count)
        current = read(report['current_path'], context_start, count)
        mix = read(DATA/row['instrumental'], context_start, count)
        other = read(DATA/tracks['other']['path'], context_start, count)
        candidates = {'current': current, 'raw': raw}
        evidence = {}
        for profile, on, off in (('gentle', -38, -44), ('strict', -28, -34)):
            gate, levels = envelope(raw, mix, on, off, .1 if family == 'brass' else .3)
            # RULE has no recovery; recovery-gated is only an offline output mask,
            # not a claim that conditional model inference has been evaluated.
            candidates['rule-'+profile] = (raw*gate).astype(np.float32)
            candidates['recovery-gated-'+profile] = (current*gate).astype(np.float32)
            evidence[profile] = {'on_relative_db': on, 'off_relative_db': off,
                                 'raw_relative_db_median': float(np.median(levels)),
                                 'active_fraction': float(np.mean(gate[offset:]>.5))}
        folder = OUT/identifier
        folder.mkdir(exist_ok=True)
        gain = min(1., .9/max(float(np.abs(a[offset:]).max()) for a in [mix, *candidates.values()]))
        players, metrics = [], []
        labels = {'current':'현재 결과', 'raw':'보완 전 RAW',
                  'rule-gentle':'RULE · 완만 · 보완 없음', 'rule-strict':'RULE · 강함 · 보완 없음',
                  'recovery-gated-gentle':'보완 결과 억제 · 완만', 'recovery-gated-strict':'보완 결과 억제 · 강함'}
        for label, audio in candidates.items():
            removed = current.astype(np.float64)-audio
            revised_other = (other.astype(np.float64)+removed).astype(np.float32)
            error = float(np.max(np.abs(audio.astype(np.float64)+revised_other-current.astype(np.float64)-other)))
            assert error < 2e-7, error
            sf.write(folder/(family+'-'+label+'-raw.wav'), audio[offset:], RATE, subtype='FLOAT')
            sf.write(folder/(family+'-'+label+'-other.wav'), revised_other[offset:], RATE, subtype='FLOAT')
            filename = family+'-'+label+'.wav'
            sf.write(folder/filename, audio[offset:]*gain, RATE, subtype='PCM_16')
            before_rms = np.sqrt(np.mean(current[offset:].astype(np.float64)**2))
            after_rms = np.sqrt(np.mean(audio[offset:].astype(np.float64)**2))
            change = float(20*np.log10((after_rms+1e-12)/(before_rms+1e-12)))
            metrics.append({'candidate':label,'rms_vs_current_db':change,'pair_error':error})
            players.append(f'<label>{labels[label]}<audio controls preload="none" src="{identifier}/{filename}"></audio></label>')
        sf.write(folder/(family+'-accompaniment.wav'), mix[offset:]*gain, RATE, subtype='PCM_16')
        status = '세 악기 없음 · 사용자 확인' if report['actual_target']=='absent_user_confirmed' else ('브라스 없음 · 사용자 확인' if family=='brass' else '기존 스트링·신디 결과 만족 · 사용자 청취')
        reports.append({'analysis_id':identifier,'name':name,'family':family,'start_sec':preview_start/RATE,
                        'end_sec':end/RATE,'label':status,'thresholds':evidence,'metrics':metrics,'common_preview_gain':gain})
        cards.append(f'<section><h2>{html.escape(name)} · {family}</h2><p>{preview_start/RATE:.1f}–{end/RATE:.1f}초 · {status} · 공통 음량 ×{gain:.3f}</p><label>반주<audio controls preload="none" src="{identifier}/{family}-accompaniment.wav"></audio></label>{"".join(players)}</section>')
    assert reports
    (OUT/'report.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'comparison.html').write_text('<!doctype html><html lang="ko"><meta charset="utf-8"><title>누출 억제 RULE 비교</title><style>body{background:#11131b;color:#e5e7ed;font-family:system-ui;margin:36px;max-width:1000px}section{background:#202330;padding:24px;margin:20px 0;border-radius:12px}label{display:block;margin:14px 0}audio{display:block;width:100%;margin-top:6px}p{color:#adb4c7}</style><h1>음량 기반 누출 억제 비교</h1><p>서비스 미적용. 두 강도는 실험 후보이며 악기 존재 판정이 아닙니다. RULE은 RAW만 사용합니다. 보완 결과 억제는 RAW 음량으로 CURRENT를 감쇠한 비교용 결과이며, 조건부 보완 추출을 다시 실행한 FULL-GATED가 아닙니다. 각 후보는 개별 트랙 실험이며 합계 보존용 나머지도 별도 저장했습니다. 같은 비교 음량을 사용합니다.</p>'+''.join(cards)+'</html>',encoding='utf-8')
    print(json.dumps([{'id':r['analysis_id'],'family':r['family'],'metrics':r['metrics']} for r in reports]))


if __name__ == '__main__':
    main()
