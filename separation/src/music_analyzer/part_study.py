"""Small, reproducible experiments for musical parts (not dry/wet separation).

Only known synthetic stems have reference metrics. Real-song diagnostics are not accuracy scores.
Production inference presets are unchanged.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

import numpy as np
import soundfile as sf

from .audio import RATE, write_raw
from .common import project_root, read_json, write_json, sha256_file


PROMPTS = {
    "guitar_strings": {
        "baseline": ["electric guitar", "orchestral strings"],
        "a": ["distorted electric guitar playing with a pick", "violins and bowed orchestral strings playing sustained notes"],
        "b": ["violins and bowed orchestral strings playing sustained notes", "distorted electric guitar playing with a pick"],
        "labels": ["electric_guitar", "strings"],
    },
    "guitar": {
        "baseline": ["An electric lead guitar playing a melodic solo", "Rhythm guitar strumming chords"],
        "a": ["electric guitar playing a single note lead melody", "electric rhythm guitar playing repeated chords"],
        "b": ["electric rhythm guitar playing repeated chords", "electric guitar playing a single note lead melody"],
        "labels": ["lead_guitar", "rhythm_guitar"],
    },
    "other": {
        "baseline": ["A sustained synthesizer pad playing in the background", "Electric guitar, piano, drums and singing"],
        "a": ["synthesizer pad playing sustained chords", "synthesizer playing a rhythmic arpeggio melody"],
        "b": ["synthesizer playing a rhythmic arpeggio melody", "synthesizer pad playing sustained chords"],
        "labels": ["synth_pad", "synth_arp"],
    },
}


def diagnostics(source, first, second):
    """Duplicate/energy diagnostics; no source identity or separation success claim."""
    arrays = [np.asarray(item, dtype=np.float64) for item in (source, first, second)]
    if any(item.shape != arrays[0].shape or item.ndim != 2 or not np.isfinite(item).all() for item in arrays):
        raise ValueError("Diagnostics require matching finite stereo timelines")
    flat = [item.reshape(-1) for item in arrays]
    energy = [float(np.dot(item, item)) for item in flat]
    denom = math.sqrt(energy[1] * energy[2])
    correlation = float(np.dot(flat[1], flat[2]) / denom) if denom > 1e-12 else None
    return {
        "waveform_correlation": correlation,
        "output_energy_ratios": [item / energy[0] if energy[0] > 1e-12 else None for item in energy[1:]],
        "sum_error_rms": float(np.sqrt(np.mean((arrays[0] - arrays[1] - arrays[2]) ** 2))),
        "accuracy_score": None,
        "warning": "Correlation, energy and reconstruction do not establish distinct musical parts.",
    }


def reference_metrics(estimate, target, interference):
    """Ground-truth-only SI-SDR and fitted source coefficients (not real-song labels)."""
    signals = [np.asarray(item, dtype=np.float64).reshape(-1) for item in (estimate, target, interference)]
    if any(item.shape != signals[0].shape or not np.isfinite(item).all() for item in signals):
        raise ValueError("Reference signals must match")
    y, a, b = signals
    a = a - a.mean(); b = b - b.mean(); y = y - y.mean()
    target_energy = float(a @ a)
    projected = a * (float(y @ a) / target_energy) if target_energy > 1e-12 else np.zeros_like(a)
    projection_energy = float(projected @ projected)
    error = y - projected
    score = 10 * math.log10((projection_energy + 1e-12) / (float(error @ error) + 1e-12)) if target_energy > 1e-12 and float(y @ y) > 1e-12 else None
    coefficients = np.linalg.lstsq(np.column_stack([a, b]), y, rcond=None)[0]
    return {"si_sdr_db": score, "target_coefficient": float(coefficients[0]), "interference_coefficient": float(coefficients[1])}


def synth_controls(folder, duration=20):
    """Known musical lines and a one-part+FX negative control. Not a realistic guitar dataset."""
    folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
    frames = round(duration * RATE)
    pad = np.zeros(frames, dtype=np.float64); arp = np.zeros(frames, dtype=np.float64)
    def tone(freq, t, count):
        return sum(np.sin(2 * np.pi * freq * h * t + .11 * h) / h ** 1.5 for h in range(1, count + 1))
    for start in np.arange(0, duration, 4):
        offset = round(start * RATE); n = min(round(4 * RATE), frames - offset); t = np.arange(n) / RATE
        envelope = np.minimum(1, t / .5) * np.minimum(1, (n / RATE - t) / .6)
        chord = (130.8128, 164.8138, 195.9977) if int(start / 4) % 2 == 0 else (110, 130.8128, 164.8138)
        pad[offset:offset+n] += .065 * envelope * sum(tone(freq, t, 4) for freq in chord)
    for index, start in enumerate(np.arange(0, duration, .4)):
        offset = round(start * RATE); n = min(round(.36 * RATE), frames - offset); t = np.arange(n) / RATE
        freq = (523.2511, 659.2551, 783.9909, 987.7666)[index % 4]
        envelope = np.minimum(1, t / .008) * np.exp(-t * 11) * np.minimum(1, (n / RATE - t) / .02)
        arp[offset:offset+n] += .18 * envelope * tone(freq, t, 6)
    def wet(signal, pan):
        stereo = np.column_stack([signal * (1-pan), signal * pan])
        for delay, gain in ((.18, .24), (.37, .15), (.61, .08)):
            shift = round(delay * RATE)
            stereo[shift:] += gain * np.column_stack([signal[:-shift] * pan, signal[:-shift] * (1-pan)])
        return stereo.astype(np.float32)
    pad, arp = wet(pad, .38), wet(arp, .66)
    write_raw(folder / "pad.wav", pad); write_raw(folder / "arp.wav", arp)
    write_raw(folder / "two_parts.wav", pad + arp)
    write_raw(folder / "one_part_with_fx.wav", pad)
    # Reference prompts use clean, separately known stems only in this synthetic control.
    for label, audio in (("pad", pad), ("arp", arp)):
        write_raw(folder / (label + "_reference.wav"), audio[:RATE*5])
    return [{"name": "synth_two_known_parts", "family": "other", "input": str(folder / "two_parts.wav"),
             "truth": [str(folder / "pad.wav"), str(folder / "arp.wav")], "reference": [str(folder / "pad_reference.wav"), str(folder / "arp_reference.wav")]},
            {"name": "synth_one_part_with_fx", "family": "other", "input": str(folder / "one_part_with_fx.wav"),
             "single_part_control": True}]


def infer_plan(plan_path):
    """Run in existing clapsep-env, loading pinned weights once for the entire comparison."""
    cache = project_root() / "data/separation/runtime/part-study-numba-cache"
    cache.mkdir(parents=True, exist_ok=True)
    os.environ["NUMBA_CACHE_DIR"] = str(cache)
    import tempfile
    tempfile.tempdir = str(cache)
    from scipy.signal import resample_poly
    from filelock import FileLock
    from .audiosep_experiment import restore_channel
    from .roformer_runner import overlap_infer
    plan_path = Path(plan_path).resolve(); plan = read_json(plan_path)
    root = Path(plan["data_root"]).resolve(); repo = root / "tools/CLAPSepInference"
    registration = read_json(project_root() / "separation/configs/models/clapsep.json")
    for name, digest in registration["code_hashes"].items():
        if sha256_file(repo / name) != digest: raise ValueError("Pinned CLAPSep code changed")
    for artifact in registration["artifacts"]:
        if sha256_file(repo / "model" / artifact["filename"]) != artifact["sha256"]: raise ValueError("Pinned weights changed")
    runtime = root / "runtime"; runtime.mkdir(parents=True, exist_ok=True)
    os.environ["WANDB_DISABLED"] = "true"
    print("Verifying pinned weights complete; acquiring GPU locks", flush=True)
    with FileLock(str(runtime / "supervisor.lock"), timeout=0), FileLock(str(runtime / "gpu-execution.lock"), timeout=0):
        sys.path.insert(0, str(repo))
        import torch
        from model.CLAPSep import CLAPSep
        if not torch.cuda.is_available(): raise ValueError("CUDA required")
        torch.manual_seed(0); np.random.seed(0)
        torch.set_num_threads(4)
        config = {"lan_embed_dim":1024,"depths":[1,1,1,1],"embed_dim":128,"encoder_embed_dim":128,"phase":False,"spec_factor":8,"d_attn":640,"n_masker_layer":3,"conv":False}
        import faulthandler
        faulthandler.dump_traceback_later(30, repeat=True)
        print("Constructing CLAPSep", flush=True)
        with contextlib.redirect_stdout(io.StringIO()):
            model = CLAPSep(config, str(repo / "model/music_audioset_epoch_15_esc_90.14.pt"))
        print("Loading separator checkpoint", flush=True)
        state = torch.load(repo / "model/best_model.ckpt", map_location="cpu", weights_only=True)
        mismatch = model.load_state_dict(state, strict=False)
        required = {name for name, parameter in model.named_parameters() if parameter.requires_grad}
        if mismatch.unexpected_keys or required.intersection(mismatch.missing_keys): raise ValueError("Checkpoint mismatch")
        model.eval().cuda(); model.clap_model.device = torch.device("cuda")
        faulthandler.cancel_dump_traceback_later()
        print("Model ready", flush=True)
        for case in plan["cases"]:
            source_path = Path(case["input"])
            if sha256_file(source_path) != case["input_sha256"]: raise ValueError("Study input changed")
            source, rate = sf.read(source_path, dtype="float32", always_2d=True)
            duration_limit = 900 if case.get("full_song_study") is True else 30
            if rate != RATE or source.shape[1] != 2 or not 1 <= len(source) / RATE <= duration_limit or not np.isfinite(source).all(): raise ValueError("Invalid study stereo source")
            native = resample_poly(source.T, 320, 441, axis=1).astype(np.float32)
            out = Path(case["output"]); out.mkdir(parents=True, exist_ok=True)
            write_raw(out / "input.wav", source)
            results = {}
            queries = [("baseline", PROMPTS[case["family"]]["baseline"], None),
                       ("part_a", PROMPTS[case["family"]]["a"], None),
                       ("part_b", PROMPTS[case["family"]]["b"], None)]
            if case.get("reference"):
                queries += [("ref_a", PROMPTS[case["family"]]["a"], case["reference"]),
                            ("ref_b", PROMPTS[case["family"]]["b"], list(reversed(case["reference"])))]
            if "queries" in case:
                selected = case["queries"]
                if not isinstance(selected, list) or not selected or len(set(selected)) != len(selected) or not set(selected).issubset({q[0] for q in queries}):
                    raise ValueError("Invalid study query selection")
                queries = [query for query in queries if query[0] in selected]
            for label, texts, references in queries:
                started = time.perf_counter(); torch.cuda.reset_peak_memory_stats()
                with torch.inference_mode():
                    positive, negative = torch.chunk(model.clap_model.get_text_embedding(texts, use_tensor=True), 2, dim=0)
                    if references:
                        samples = []
                        for reference in references:
                            audio, ref_rate = sf.read(reference, dtype="float32", always_2d=True)
                            if ref_rate != RATE or not 1 <= len(audio) / RATE <= 10 or not np.isfinite(audio).all(): raise ValueError("Invalid reference audio")
                            samples.append(resample_poly(audio.mean(axis=1), 160, 147).astype(np.float32))
                        if len(samples[0]) != len(samples[1]): raise ValueError("Reference lengths must match")
                        # CLAP audio queries require 48 kHz. Separate from the separator's 32 kHz input.
                        reference_embeddings = model.clap_model.get_audio_embedding_from_data(torch.from_numpy(np.stack(samples)).cuda(), use_tensor=True)
                        model.features.clear()  # Audio query forward hooks share the separation encoder.
                        ref_pos, ref_neg = torch.chunk(reference_embeddings, 2, dim=0)
                        positive = .5 * positive + .5 * ref_pos; negative = .5 * negative + .5 * ref_neg
                    def infer(piece):
                        channels = []
                        for channel in piece:
                            prediction = model.inference_from_data(torch.from_numpy(channel)[None,:].cuda(), positive, negative)
                            channels.append(prediction[0].float().cpu().numpy())
                        return np.stack(channels)
                    estimate = overlap_infer(native, 320000, .5, infer)
                    restored = np.column_stack([restore_channel(channel, len(source)) for channel in estimate])
                write_raw(out / (label + ".wav"), restored)
                results[label] = {"path": label + ".wav", "sha256": sha256_file(out / (label + ".wav")), "positive": texts[0], "negative": texts[1],
                                  "reference": references, "reference_sha256": [sha256_file(Path(p)) for p in references] if references else None,
                                  "wall_sec": time.perf_counter() - started, "peak_allocated_bytes": torch.cuda.max_memory_allocated()}
                print(case["name"], label, "READY", flush=True)
            metrics = {}
            if "baseline" in results:
                baseline, _ = sf.read(out / "baseline.wav", dtype="float32", always_2d=True)
                write_raw(out / "baseline_residual.wav", source - baseline)
                metrics["baseline_target_residual"] = diagnostics(source, baseline, source - baseline)
            if {"part_a", "part_b"}.issubset(results):
                a, _ = sf.read(out / "part_a.wav", dtype="float32", always_2d=True)
                b, _ = sf.read(out / "part_b.wav", dtype="float32", always_2d=True)
                write_raw(out / "unassigned.wav", source - a - b)
                metrics["independent_text_parts"] = diagnostics(source, a, b)
            if case.get("truth"):
                truth = [sf.read(p, dtype="float32", always_2d=True)[0] for p in case["truth"]]
                for label in results:
                    value = sf.read(out / (label + ".wav"), dtype="float32", always_2d=True)[0]
                    target_index = 1 if label.endswith("b") else 0
                    metrics[label] = reference_metrics(value, truth[target_index], truth[1-target_index])
                metrics["input_as_pad"] = reference_metrics(source, truth[0], truth[1])
                metrics["input_as_arp"] = reference_metrics(source, truth[1], truth[0])
            if case.get("single_part_control") and "part_b" in results:
                b, _ = sf.read(out / "part_b.wav", dtype="float32", always_2d=True)
                metrics["single_part_control"] = {"second_part_energy_ratio": float(np.sum(b.astype(np.float64)**2) / max(1e-12, np.sum(source.astype(np.float64)**2))), "interpretation": "No second part exists. Any audible second musical line is false extraction; FX tails are not a second part."}
            manifest = {"case": case, "state": "CANDIDATE_READY", "model": registration, "model_inference_performed": True,
                        "timeline": {"sample_rate": RATE, "channels": 2, "num_frames": len(source)}, "results": results, "metrics": metrics,
                        "quality_improvement_verified": False, "channel_strategy": "independent mono inference; stereo identity not guaranteed",
                        "note": "Selected queries are independent, possibly overlapping estimates. Any saved residual is a signed difference, not an instrument."}
            write_json(out / "manifest.json", manifest)
    print("STUDY COMPLETE", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--infer-plan", type=Path, required=True)
    args = parser.parse_args()
    infer_plan(args.infer_plan)


if __name__ == "__main__": main()
