"""READ-ONLY benchmark of persistent final-stem formats: Float32 WAV (current) vs PCM24 WAV vs FLAC 24-bit.

Inputs are real final stems from the library (nothing there is changed); converted files go to data/audit/format-bench and are removed.
2-track / 6-track / 13-track sets come from library analyses (basic_2, basic_6, final_11). Metrics per set and format: size, encode/decode time,
peak RSS, process CPU seconds, max quantization error, clipped samples and the effect on the partition sum.
usage: audio-format-benchmark.py    -> data/audit/formats.json
"""
import json, shutil, sys, threading, time
from pathlib import Path
import numpy as np, psutil, soundfile as sf

ROOT = Path(__file__).resolve().parents[1]; DATA = ROOT / "data/separation"; OUT = ROOT / "data/audit"; WORK = OUT / "format-bench"
records = {}
for path in (DATA / "web").glob("analysis_*/record.json"):
    r = json.loads(path.read_text(encoding="utf-8")); records[path.parent.name] = r
pick = {}
for i, r in records.items():
    if r.get("state") == "SUCCEEDED" and r.get("name") == "오늘을 채워 가" and r["model"] in ("basic_6", "final_11"):
        pick[{"basic_6": "6-track", "final_11": "13-track"}[r["model"]]] = i
pick["2-track"] = next(i for i, r in records.items() if r.get("model") == "basic_2" and r.get("state") == "SUCCEEDED")
process = psutil.Process()


def measure(fn):
    """run fn, return (result, wall seconds, cpu seconds, peak RSS delta MB)"""
    peak = [process.memory_info().rss]; stop = threading.Event()
    def watch():
        while not stop.is_set():
            peak[0] = max(peak[0], process.memory_info().rss); time.sleep(.01)
    base = process.memory_info().rss; t = threading.Thread(target=watch, daemon=True); t.start()
    c0 = process.cpu_times(); w0 = time.perf_counter()
    value = fn()
    wall = time.perf_counter() - w0; c1 = process.cpu_times(); stop.set(); t.join()
    return value, wall, (c1.user - c0.user) + (c1.system - c0.system), max(0, peak[0] - base) / 2**20


result = {}
for label, identifier in sorted(pick.items()):
    record = records[identifier]; folder = DATA / "web" / identifier
    files = {t["family"]: DATA / t["path"] for t in record["tracks"]}
    original = DATA / record["original"]
    seconds = sf.info(original).duration
    data = {f: sf.read(p, dtype="float32", always_2d=True)[0] for f, p in files.items()}
    mix = sf.read(original, dtype="float32", always_2d=True)[0]
    exact_sum = np.sum([a.astype(np.float64) for a in data.values()], axis=0)
    entry = {"analysis": identifier[-8:], "name": record.get("name"), "preset": record["model"], "seconds": round(seconds, 1), "stems": len(files),
             "peak_over_1": int(sum(np.sum(np.abs(a) > 1.0) for a in data.values())), "formats": {}}
    for fmt, kwargs, ext in (("float32_wav", dict(format="WAV", subtype="FLOAT"), ".wav"), ("pcm24_wav", dict(format="WAV", subtype="PCM_24"), ".wav"),
                             ("flac24", dict(format="FLAC", subtype="PCM_24"), ".flac")):
        out = WORK / label / fmt; shutil.rmtree(out, ignore_errors=True); out.mkdir(parents=True)
        def encode():
            for family, audio in data.items():
                sf.write(out / (family + ext), audio, 44100, **kwargs)
        _, enc_wall, enc_cpu, enc_ram = measure(encode)
        size = sum((out / (f + ext)).stat().st_size for f in data)
        def decode():
            return {f: sf.read(out / (f + ext), dtype="float32", always_2d=True)[0] for f in data}
        back, dec_wall, dec_cpu, dec_ram = measure(decode)
        err = max(float(np.max(np.abs(back[f].astype(np.float64) - data[f]))) for f in data)
        summed = np.sum([a.astype(np.float64) for a in back.values()], axis=0)
        # download as WAV (what a user would get from a FLAC store): decode + write PCM24 WAV
        def to_wav():
            tmp = out / "dl"; tmp.mkdir(exist_ok=True)
            for f in data:
                sf.write(tmp / (f + ".wav"), sf.read(out / (f + ext), dtype="float32", always_2d=True)[0], 44100, subtype="PCM_24")
        _, dl_wall, _, _ = measure(to_wav)
        entry["formats"][fmt] = {"bytes": size, "mb": round(size / 2**20, 1), "mb_per_audio_minute_all_stems": round(size / 2**20 / (seconds / 60), 1),
                                 "encode_s": round(enc_wall, 2), "encode_cpu_s": round(enc_cpu, 2), "encode_peak_ram_mb": round(enc_ram, 1),
                                 "decode_s": round(dec_wall, 2), "decode_cpu_s": round(dec_cpu, 2), "decode_peak_ram_mb": round(dec_ram, 1),
                                 "wav_download_s": round(dl_wall, 2), "max_abs_error_vs_float32": err,
                                 "lossless_vs_float32": err == 0.0, "partition_error_vs_original_after": float(np.max(np.abs(summed - mix.astype(np.float64)))),
                                 "partition_error_vs_original_before": float(np.max(np.abs(exact_sum - mix.astype(np.float64))))}
        shutil.rmtree(out, ignore_errors=True)
        print(label, fmt, entry["formats"][fmt]["mb"], "MB", flush=True)
    result[label] = entry
shutil.rmtree(WORK, ignore_errors=True)
json.dump(result, open(OUT / "formats.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
