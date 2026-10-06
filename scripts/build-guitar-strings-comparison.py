"""Create Orange guitar/strings listening candidates and diagnostic windows."""
import json
from pathlib import Path
import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / "data/part-studies/guitar-strings-orange"


def read(path):
    with sf.SoundFile(path) as source:
        assert (source.samplerate, source.channels) == (44100, 2)
        data = source.read(20 * 44100, dtype="float32", always_2d=True)
    assert data.shape == (20 * 44100, 2) and np.isfinite(data).all()
    return data


def main():
    previous = ROOT / "data/part-studies/mega53-extended/orange"
    paths = {
        "previous": (" 기존 전용 출력", previous / "electric-guitar.wav", previous / "strings.wav"),
        "bowed": ("현악 전용 후보", STUDY / "bowed-full/electric-guitar.wav", STUDY / "bowed-full/bowed_strings.wav"),
        "mix": ("CLAPSep · 원곡 입력", STUDY / "mix/part_a.wav", STUDY / "mix/part_b.wav"),
        "parent": ("CLAPSep · 기타 입력", STUDY / "guitar-parent/part_a.wav", STUDY / "guitar-parent/part_b.wav"),
    }
    arrays = {key: (read(a), read(b)) for key, (_, a, b) in paths.items()}
    metrics = []
    for key, (a, b) in arrays.items():
        for start, end in ((0, 8), (9, 20)):
            x = a[start*44100:end*44100].astype(np.float64).ravel()
            y = b[start*44100:end*44100].astype(np.float64).ravel()
            denominator = np.sqrt((x @ x) * (y @ y))
            metrics.append({"route": key, "start_sec": start, "end_sec": end,
                            "correlation": float(x @ y / denominator) if denominator > 0 else None,
                            "guitar_rms": float(np.sqrt(np.mean(x*x))), "strings_rms": float(np.sqrt(np.mean(y*y)))})
    preview = STUDY / "preview"
    preview.mkdir(exist_ok=True)
    rows, levels = [], []
    original = read(STUDY / "original.wav")
    sf.write(preview / "original.wav", original * min(1, .9 / max(float(np.max(np.abs(original))), 1e-12)), 44100, subtype="PCM_16")
    for key, (a, b) in arrays.items():
        cards = []
        for label, samples in (("electric", a), ("strings", b)):
            rms = float(np.sqrt(np.mean(samples.astype(np.float64)**2)))
            peak = float(np.max(np.abs(samples)))
            gain = min(4, .06 / max(rms, 1e-12), .9 / max(peak, 1e-12))
            filename = f"{key}-{label}.wav"
            sf.write(preview / filename, samples * gain, 44100, subtype="PCM_16")
            levels.append({"route": key, "target": label, "gain": gain})
            cards.append(f'<div><h3>{"일렉기타" if label=="electric" else "스트링"}</h3><audio controls preload="none" src="preview/{filename}"></audio></div>')
        rows.append(f'<section><h2>{paths[key][0]}</h2><div class="cards">'+''.join(cards)+'</div></section>')
    page = '''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Orange 일렉·스트링 비교</title><style>body{background:#101620;color:#edf2fa;font:16px system-ui;max-width:960px;margin:32px auto;padding:0 20px}p{color:#c0cede;line-height:1.6}section{background:#192638;border-radius:14px;padding:20px;margin:20px 0}.cards{display:flex;gap:30px;flex-wrap:wrap}.cards>div{flex:1;min-width:280px}audio{width:100%;max-width:420px}h2{font-size:20px}</style><h1>Orange · 일렉기타와 스트링</h1><p>0–20초 구간입니다. 9초 전에는 스트링의 잘못된 검출을, 9초 이후에는 두 연주의 구분을 확인해주세요. 청취용 RMS만 조정했고 raw는 보존했습니다.</p><h2>원곡</h2><audio controls preload="none" src="preview/original.wav"></audio>'''+''.join(rows)+'''<script>document.querySelectorAll('audio').forEach(a=>a.addEventListener('play',()=>document.querySelectorAll('audio').forEach(b=>{if(a!==b)b.pause()})))</script></html>'''
    (STUDY / "comparison.html").write_text(page, encoding="utf-8")
    (STUDY / "diagnostics.json").write_text(json.dumps({"metrics":metrics,"preview_levels":levels,"accuracy_score":None}, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
