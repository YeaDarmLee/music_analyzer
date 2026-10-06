"""Build a local listening page from the two extended Mega53 study results."""
import html
import json
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / "data/part-studies/mega53-extended"
LABELS = {"acoustic-guitar": "어쿠스틱 기타", "electric-guitar": "일렉기타", "synth": "신스", "brass": "브라스", "strings": "스트링"}
BASELINES = {
    "miracle": ROOT / "data/separation/jobs/job_33da672399fc414a891eec31e5b169cb/result/stems",
    "orange": ROOT / "data/reset-backups/reset-20261006-193853/jobs/job_2b1a4403cb204f27b823800f2674a529/result/stems",
}
NAMES = {"miracle": "미라클 제너레이션 · 기타 분리 비교", "orange": "SPYAIR Orange · 신스·브라스·스트링 비교"}


def excerpt(path, start):
    with sf.SoundFile(path) as source:
        if source.samplerate != 44100 or source.channels != 2:
            raise ValueError("Expected stereo canonical sample rate")
        source.seek(start * 44100)
        return source.read(20 * 44100, dtype="float32", always_2d=True)


def main():
    preview = STUDY / "preview"
    preview.mkdir(exist_ok=True)
    sections, levels = [], []
    for song, name in NAMES.items():
        report = json.loads((STUDY / song / "benchmark.json").read_text(encoding="utf-8"))
        if report["start_sec"] != 0:
            raise ValueError("Expected full-song results")
        for start in (0, 40, 100):
            cards = []
            original_name = f"{song}-{start}-original.wav"
            original = excerpt(Path(report["source_path"]), start)
            peak = float(np.max(np.abs(original)))
            sf.write(preview / original_name, original * min(1, .9 / max(peak, 1e-12)), 44100, subtype="PCM_16")
            for label, title in LABELS.items():
                current = excerpt(STUDY / song / (label + ".wav"), start)
                old_label = "guitar" if label in ("acoustic-guitar", "electric-guitar") else "other"
                previous = excerpt(BASELINES[song] / (old_label + ".wav"), start)
                values = (current, previous)
                rms = [float(np.sqrt(np.mean(x.astype(np.float64) ** 2))) for x in values]
                peaks = [float(np.max(np.abs(x))) for x in values]
                target = min([.06] + [.9 * r / p for r, p in zip(rms, peaks) if r > 0 and p > 0])
                players = []
                for route, text, samples, level in zip(("new", "old"), ("전용 출력", "기존 기타" if old_label == "guitar" else "기존 신스 표시 출력"), values, rms):
                    gain = min(4, target / level) if level > 0 else 1
                    filename = f"{song}-{start}-{label}-{route}.wav"
                    sf.write(preview / filename, samples * gain, 44100, subtype="PCM_16")
                    levels.append({"song": song, "start_sec": start, "target": label, "route": route, "gain": gain, "rms_before": level})
                    players.append(f'<p>{text}</p><audio controls preload="none" src="preview/{filename}"></audio>')
                cards.append(f'<article><h3>{title}</h3>'+''.join(players)+'</article>')
            sections.append(f'<section data-song="{song}" data-start="{start}"><h2>{html.escape(name)} · {start}–{start+20}초</h2><p>원곡</p><audio controls preload="none" src="preview/{original_name}"></audio><div class="cards">'+''.join(cards)+'</div></section>')
    page = '''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Mega53 다섯 악기 비교</title><style>body{font:16px system-ui;background:#101620;color:#edf2fa;max-width:1100px;margin:32px auto;padding:0 20px}p{color:#bac7d8;line-height:1.6}select{font:inherit;padding:10px;border-radius:8px;margin:8px 12px 8px 0}section{margin-top:24px}section[hidden]{display:none}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px;margin:24px 0}article{background:#1a2637;padding:18px;border-radius:12px}audio{width:100%;max-width:420px}h2{font-size:21px}h3{margin-top:0}</style><h1>신스·브라스·스트링·두 기타 비교</h1><p>원곡 직접 입력으로 추출했습니다. 청취용 음량만 조정했으며 raw 원본은 별도 보존했습니다. 음량 증폭은 최대 4배로 제한했습니다.</p><select id="song" aria-label="곡"><option value="miracle">미라클 제너레이션</option><option value="orange">SPYAIR Orange</option></select><select id="interval" aria-label="구간"><option value="0">0–20초</option><option value="40">40–60초</option><option value="100">100–120초</option></select>'''+''.join(sections)+'''<script>const song=document.querySelector('#song'),interval=document.querySelector('#interval');function update(){document.querySelectorAll('audio').forEach(a=>a.pause());document.querySelectorAll('section').forEach(s=>s.hidden=s.dataset.song!==song.value||s.dataset.start!==interval.value)}song.onchange=interval.onchange=update;document.querySelectorAll('audio').forEach(a=>a.addEventListener('play',()=>document.querySelectorAll('audio').forEach(b=>{if(b!==a)b.pause()})));update()</script></html>'''
    (STUDY / "comparison.html").write_text(page, encoding="utf-8")
    (preview / "levels.json").write_text(json.dumps(levels, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Created comparison.html and 66 audio excerpts")


if __name__ == "__main__":
    main()
