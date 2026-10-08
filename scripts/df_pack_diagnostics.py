"""Objective diagnostics for a rendered pack (stand-in for listening: the agent cannot hear audio)."""
import json, sys, warnings
from pathlib import Path
import numpy as np
warnings.filterwarnings("ignore")
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from data_factory.util import read_wav  # noqa: E402


def stats(x, sr=44100):
    m = x.mean(0)
    rms = float(np.sqrt((m ** 2).mean()))
    fr = m[: len(m) // 2048 * 2048].reshape(-1, 2048)
    frame_db = 20 * np.log10(np.sqrt((fr ** 2).mean(1)) + 1e-9)
    sp = np.abs(np.fft.rfft(m[: 1 << 18] * np.hanning(min(len(m), 1 << 18)), 1 << 18))
    fq = np.fft.rfftfreq(1 << 18, 1 / sr)
    return {"rms_db": round(20 * np.log10(rms + 1e-9), 1), "peak": round(float(np.abs(x).max()), 3),
            "active_frac_-50dB": round(float((frame_db > -50).mean()), 2), "centroid_hz": int((sp * fq).sum() / max(sp.sum(), 1e-9)),
            "stereo_corr": round(float(np.corrcoef(x[0], x[1])[0, 1]) if x.std() > 0 else 1.0, 2)}


out = {}
for d in sorted(Path(sys.argv[1]).iterdir()):
    if not d.is_dir():
        continue
    meta = json.loads((d / "metadata.json").read_text())
    out[d.name] = {s: stats(read_wav(d / f"{s}.wav")[0]) for s in ["mix"] + meta["active_stems"]}
Path(sys.argv[2]).write_text(json.dumps(out, indent=1))
for k, v in out.items():
    print(k, {s: (e["rms_db"], e["centroid_hz"], e["active_frac_-50dB"]) for s, e in v.items()})
