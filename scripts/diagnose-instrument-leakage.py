"""Offline CURRENT/RAW comparison. Never modifies service records or source audio."""
import csv
import html
import json
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/separation'
OUT = ROOT / 'data/part-studies/instrument-leakage-diagnosis'
RATE = 44100


def rms(audio):
    return float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))


def db(value):
    return float(20 * np.log10(max(value, 1e-12)))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    reports, windows, cards = [], [], []
    for record in sorted((DATA / 'web').glob('analysis_*/record.json')):
        row = json.loads(record.read_text(encoding='utf-8'))
        if row['state'] != 'SUCCEEDED' or not row.get('instrumental'):
            continue
        folder = OUT / row['id']
        folder.mkdir(exist_ok=True)
        tracks = {t['family']: t for t in row['tracks']}
        target_label = 'absent_user_confirmed' if row['id'] == 'analysis_8842c174a4464e628994f81f911d1dca' else 'unlabelled'
        for family in ('brass', 'strings', 'synth'):
            current = tracks[family]
            recovery = row.get(family + '_recovery', {})
            raw = recovery.get('original_tracks', {}).get(family, current)
            paths = [DATA / row['instrumental'], DATA / raw['path'], DATA / current['path']]
            stats, total_error, delta_peak = [], 0., 0.
            with sf.SoundFile(paths[0]) as accompaniment, sf.SoundFile(paths[1]) as before, sf.SoundFile(paths[2]) as after:
                assert all((f.samplerate, f.channels, f.frames) == (RATE, 2, accompaniment.frames) for f in (accompaniment, before, after))
                for start in range(0, accompaniment.frames, 2 * RATE):
                    mix, a, b = [f.read(2 * RATE, dtype='float32', always_2d=True) for f in (accompaniment, before, after)]
                    assert all(np.isfinite(x).all() for x in (mix, a, b))
                    delta = b.astype(np.float64) - a
                    level, raw_level, final_level, change = map(rms, (mix, a, b, delta))
                    error = float(np.max(np.abs(delta)))
                    total_error = max(total_error, error)
                    delta_peak = max(delta_peak, error)
                    item = dict(analysis_id=row['id'], family=family, start_sec=start / RATE,
                                end_sec=(start + len(mix)) / RATE, accompaniment_rms=level,
                                raw_rms=raw_level, current_rms=final_level, added_rms=change,
                                raw_relative_db=db(raw_level) - db(level),
                                current_relative_db=db(final_level) - db(level),
                                current_vs_raw_db=db(final_level) - db(raw_level),
                                actual_target=target_label, artifact='unlabelled')
                    stats.append(item)
                    windows.append(item)
            # The same source guarantees no separate brass recovery caused its leakage.
            if family == 'brass':
                assert total_error == 0
            strongest = max(stats, key=lambda x: x['added_rms'] if recovery else x['raw_rms'])
            start = max(0, strongest['start_sec'] - 8)
            end = min(row['duration'], start + 20)
            preview_arrays = {}
            for label, path in zip(('accompaniment', 'raw', 'current'), paths):
                with sf.SoundFile(path) as f:
                    f.seek(round(start * RATE))
                    preview_arrays[label] = f.read(round((end - start) * RATE), dtype='float32', always_2d=True)
            preview_arrays['added'] = preview_arrays['current'] - preview_arrays['raw']
            # Common gain preserves RAW/CURRENT relative level; no per-stem normalization.
            peak = max(float(np.abs(a).max()) for a in preview_arrays.values())
            gain = min(1., .9 / max(peak, 1e-12))
            players = []
            for label, audio in preview_arrays.items():
                filename = family + '-' + label + '.wav'
                sf.write(folder / filename, audio * gain, RATE, subtype='PCM_16')
                players.append(f'<label>{label}<audio controls preload="none" src="{row["id"]}/{filename}"></audio></label>')
            report = dict(analysis_id=row['id'], name=row['name'], family=family,
                          raw_path=str(paths[1]), current_path=str(paths[2]), recovery_applied=bool(recovery),
                          max_current_minus_raw=delta_peak, preview_start_sec=start, preview_end_sec=end,
                          preview_gain=gain, actual_target=target_label,
                          strongest_window=strongest)
            reports.append(report)
            cards.append(f'<section><h2>{html.escape(row["name"])} · {family}</h2><p>{start:.1f}–{end:.1f}초 · 공통 음량 ×{gain:.3f} · {"사용자 확인: 세 악기 모두 없음" if target_label != "unlabelled" else "존재 여부 미라벨"}</p>{"".join(players)}</section>')
    assert reports, 'No completed analyses available'
    (OUT / 'report.json').write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding='utf-8')
    with (OUT / 'windows.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(windows[0]))
        writer.writeheader()
        writer.writerows(windows)
    page = '<!doctype html><html lang="ko"><meta charset="utf-8"><title>브라스·스트링·신디 누출 진단</title><style>body{background:#11131b;color:#e5e7ed;font-family:system-ui;margin:36px;max-width:1000px}section{background:#202330;padding:24px;margin:20px 0;border-radius:12px}label{display:block;margin:14px 0}audio{display:block;width:100%;margin-top:6px}p{color:#adb4c7}</style><h1>CURRENT / RAW 비교</h1><p>서비스 결과를 수정하지 않은 진단입니다. 자동 선택 구간은 보완 변화 또는 기본 출력이 큰 구간이며, 악기가 없는 구간이라는 뜻은 아닙니다. added는 CURRENT−RAW입니다. RULE·CLASSIFIER·FULL-GATED는 아직 실행하지 않았습니다.</p>' + ''.join(cards) + '</html>'
    (OUT / 'comparison.html').write_text(page, encoding='utf-8')
    print(json.dumps([dict(analysis_id=r['analysis_id'], family=r['family'],
                           difference=r['max_current_minus_raw'], strongest_window=r['strongest_window']) for r in reports]))


if __name__ == '__main__':
    main()
