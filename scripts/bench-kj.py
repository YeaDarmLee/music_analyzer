"""KJ diagnostic benchmark (plan section 5: K1 baseline, K2 input-path diagnosis, vocal residue probe). Diagnosis only: no pipeline change.

6 fixed songs from song/, one 40 s window each (loudest window between 15% and 85% of the song, recorded in the report).
Per clip, using the production parameters (KJ: 8 s chunks, overlap 0.4; core4: 10 s, 0.4; both fp16):
  KJ(mix) -> vocals, inst = mix - vocals                               (product stage 1)
  core4(inst) -> piano/guitar/bass/drums, other = inst - sum(4)        (product stage 2)
  K2: core4(mix) and core4(mix * -6 dB / -12 dB) as reference/diagnostic drums (never a product path)
  K5 probe: KJ(inst) -> residual 'vocals' energy left in inst
No ground truth exists for real songs: every number is a relative reference indicator, not a true SDR/leakage.
All files live in one RunContext under MUSIC_TEST_ROOT; the small JSON report is copied to test-workspace/reports/.

usage: bench-kj.py [--seconds 40] [--keep-listening]
"""
import argparse, json, os, subprocess, sys, time
from pathlib import Path
import numpy as np
from music_analyzer.common import project_root
from music_analyzer import testws

SONGS = {"Blueming": "Blueming", "Orange": "스파이에어(SPYAIR) - Orange", "Horizon": "사건의 지평선", "GoodnessOfGod": "Goodness of God",
         "Sparkle": "Sparkle", "Fiction": "imase - Fiction"}
SR = 44100
BANDS = {"low<150Hz": (0, 150), "mid": (150, 5000), "high>5k": (5000, 22050)}


def find_song(key):
    hits = [p for p in (project_root() / "song").glob("*.mp3") if key in p.name]
    assert len(hits) == 1, (key, hits)
    return hits[0]


def decode(ctx, path):
    r = ctx.run(["ffmpeg", "-v", "error", "-i", str(path), "-ar", str(SR), "-ac", "2", "-f", "f32le", "-"], capture_output=True, check=True)
    return np.frombuffer(r.stdout, np.float32).reshape(-1, 2).copy()


def pick_window(x, seconds):
    n = int(seconds * SR); hop = SR * 5
    lo, hi = int(len(x) * .15), int(len(x) * .85) - n
    starts = range(lo, max(lo + 1, hi), hop)
    score = lambda s: float(np.mean(x[s:s + n] ** 2))
    s = max(starts, key=score)
    return s, x[s:s + n]


def db(x):
    return float(20 * np.log10(np.sqrt(np.mean(np.asarray(x, np.float64) ** 2)) + 1e-12))


def band_db(x, torch):
    """Mean-power dB per band (STFT, both channels)."""
    t = torch.from_numpy(np.ascontiguousarray(x.T))
    spec = torch.stft(t, 4096, 1024, window=torch.hann_window(4096), return_complex=True).abs() ** 2
    freqs = torch.fft.rfftfreq(4096, 1 / SR)
    return {k: float(10 * torch.log10(spec[:, (freqs >= a) & (freqs < b)].mean() + 1e-20)) for k, (a, b) in BANDS.items()}


def cos2(a, b):
    a = a.astype(np.float64).ravel(); b = b.astype(np.float64).ravel()
    return float(np.dot(a, b) ** 2 / (np.dot(a, a) * np.dot(b, b) + 1e-20))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--seconds", type=float, default=40); ap.add_argument("--keep-listening", action="store_true")
    a = ap.parse_args()
    est = testws.estimate_gb(songs=6, seconds=a.seconds, stems=14, models=1)
    with testws.RunContext(est_gb=est, keep=a.keep_listening) as ctx:
        os.environ.update(ctx.env())  # torch/triton/numba caches and temp files stay inside the run
        import soundfile as sf, torch
        from music_analyzer.common import read_json
        from music_analyzer.roformer_runner import load_config, overlap_infer
        from music_analyzer.vendor.msst.bs_roformer import BSRoformer
        from music_analyzer.vendor.msst.mel_band_roformer import MelBandRoformer
        models_dir = project_root() / "data/separation/models"

        def load(model_id):
            reg = read_json(models_dir / model_id / "registration.json"); cfg = load_config(reg)
            bs = reg.get("engine") == "bs_roformer"
            m = BSRoformer(**cfg["model"]) if bs else MelBandRoformer(**cfg["model"], match_input_audio_length=True)
            w = torch.load(models_dir / model_id / reg["checkpoint_filename"], map_location="cpu", weights_only=True); w = w.get("state_dict", w)
            m.load_state_dict(w, strict=True); m.eval().cuda()
            return m, reg, bs

        def run(model, bs, reg, x, seg_sec, overlap=.4):
            multi = bs; chunk = round(seg_sec * SR)
            def infer(piece):
                with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
                    out = model(torch.from_numpy(piece).unsqueeze(0).cuda())[0].float().cpu().numpy()
                return out[0] if (not multi and out.ndim == 3 and out.shape[0] == 1) else out
            torch.cuda.synchronize(); torch.cuda.reset_peak_memory_stats(); t0 = time.perf_counter()
            y = overlap_infer(x.T.copy(), chunk, overlap, infer, output_stems=len(reg["source_labels"]) if multi else None)
            torch.cuda.synchronize()
            cost = {"sec": time.perf_counter() - t0, "vram_mb": torch.cuda.max_memory_allocated() / 2 ** 20}
            return ({l: e.T for l, e in zip(reg["source_labels"], y)} if multi else y.T), cost

        kj, kj_reg, kj_bs = load("melband_roformer_kj")
        c4, c4_reg, c4_bs = load("bs_roformer_core4")
        rows = []
        for name, key in SONGS.items():
            full = decode(ctx, find_song(key)); start, mix = pick_window(full, a.seconds); del full
            ctx.check_quota(int(mix.nbytes * 14))
            sf.write(ctx.inputs / f"{name}.wav", mix, SR, subtype="FLOAT")
            vocals, cost_kj = run(kj, kj_bs, kj_reg, mix, 8)
            inst = mix - vocals
            st, cost_c4 = run(c4, c4_bs, c4_reg, inst, 10)
            four = {k: st[k] for k in ("piano", "guitar", "bass", "drums")}
            other = inst - sum(four.values())
            ref, _ = run(c4, c4_bs, c4_reg, mix, 10)                                   # K2: core4 on the original mix
            ref6, _ = run(c4, c4_bs, c4_reg, mix * 10 ** (-6 / 20), 10)
            ref12, _ = run(c4, c4_bs, c4_reg, mix * 10 ** (-12 / 20), 10)
            resid, _ = run(kj, kj_bs, kj_reg, inst.astype(np.float32), 8)              # K5 probe: vocal left in inst
            dr, dref = four["drums"], ref["drums"]
            row = {"song": name, "file": find_song(key).name, "start_sec": start / SR, "mix_db": db(mix),
                   "re_mix_db": {"vocals": db(vocals) - db(mix), "inst": db(inst) - db(mix), **{k: db(v) - db(mix) for k, v in four.items()}, "other": db(other) - db(mix)},
                   "drums": {"product_re_mix_db": db(dr) - db(mix), "ref_core4_on_mix_re_mix_db": db(dref) - db(mix),
                             "survival_db": db(dr) - db(dref),
                             "survival_k2_minus6_db": db(ref6["drums"] / 10 ** (-6 / 20)) - db(dref), "survival_k2_minus12_db": db(ref12["drums"] / 10 ** (-12 / 20)) - db(dref),
                             "band_survival_db": {k: band_db(dr, torch)[k] - band_db(dref, torch)[k] for k in BANDS},
                             "ref_cos2_with_kj_vocals": cos2(dref, vocals), "ref_cos2_with_kj_inst": cos2(dref, inst), "ref_cos2_with_other": cos2(dref, other)},
                   "vocal_residue_in_inst_db": db(resid) - db(inst),
                   "sum_check_rms_db": db(vocals + inst - mix), "cost": {"kj": cost_kj, "core4": cost_c4}}
            rows.append(row)
            out = ctx.listening / name; out.mkdir()
            for tag, sig in {"mix": mix, "kj_vocals": vocals, "kj_inst": inst, "drums_product": dr, "drums_ref_on_mix": dref, "other": other, **{f"s_{k}": v for k, v in four.items() if k != "drums"}}.items():
                sf.write(out / f"{tag}.wav", np.clip(sig, -1, 1), SR, subtype="PCM_16")
            print(f"{name}: drums survival {row['drums']['survival_db']:.1f} dB, residue {row['vocal_residue_in_inst_db']:.1f} dB, kj {cost_kj['sec']:.1f}s", flush=True)
        report = {"date": time.strftime("%Y-%m-%d %H:%M"), "run_id": ctx.run_id, "params": {"kj": "8s/0.4 fp16", "core4": "10s/0.4 fp16", "window_sec": a.seconds},
                  "note": "no ground truth: relative reference indicators only", "rows": rows}
        (ctx.report / "kj_baseline.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
        out = ctx.root / "reports" / f"kj_baseline_{ctx.run_id}.json"; out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
        print("report:", out); print("run:", ctx.run_id, "listening:", ctx.listening)


if __name__ == "__main__":
    main()
