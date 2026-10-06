"""Prepare and benchmark selected official Mega53 heads without changing web defaults."""
from __future__ import annotations

import argparse
import copy
import gc
import re
import time
import urllib.request
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
import yaml
from filelock import FileLock

from .common import project_root, sha256_file, write_json
from .roformer_runner import ConfigLoader, overlap_infer

TARGETS = {1: "acoustic-guitar", 16: "electric-guitar", 38: "synth"}
EXTENDED_TARGETS = {1: "acoustic-guitar", 16: "electric-guitar", 38: "synth", 8: "brass", 37: "strings"}
BOWED_TARGETS = {1: "acoustic-guitar", 16: "electric-guitar", 38: "synth", 8: "brass", 7: "bowed_strings"}
CHECKPOINT_SHA = "c62820893bbf86d4e734f966bd142d9157cfc8bb8e79e9d8f9ea553f3ff3519f"
CONFIG_SHA = "7e198062a251587088adb91215a4f44ab59e67bd62fcc805cf54d6e7dfc51103"
URL = "https://github.com/ZFTurbo/Music-Source-Separation-Training/releases/download/v1.0.21/mvsep_mega_model_bs_roformer_53_stems_v1.ckpt"


class ConfigDumper(yaml.SafeDumper):
    pass


ConfigDumper.add_representer(tuple, lambda dumper, value: dumper.represent_sequence("tag:yaml.org,2002:python/tuple", value))


def prune_heads(weights: dict, selected=tuple(TARGETS)) -> dict:
    """Keep shared tensors unchanged and renumber selected independent heads."""
    if not selected or len(set(selected)) != len(selected) or any(i < 0 or i >= 53 for i in selected):
        raise ValueError("Invalid selected heads")
    if "state_dict" in weights:
        weights = weights["state_dict"]
    if not weights or not all(isinstance(k, str) and isinstance(v, torch.Tensor) for k, v in weights.items()):
        raise ValueError("Expected tensor state_dict")
    if all(k.startswith("module.") for k in weights):
        weights = {k[7:]: v for k, v in weights.items()}
    result, seen = {}, set()
    mapping = {old: new for new, old in enumerate(selected)}
    for key, tensor in weights.items():
        match = re.match(r"^mask_estimators\.(\d+)\.(.+)$", key)
        if match:
            head = int(match[1])
            seen.add(head)
            if head not in mapping:
                continue
            key = f"mask_estimators.{mapping[head]}.{match[2]}"
        elif key.startswith("mask_estimators."):
            raise ValueError("Malformed mask estimator key")
        result[key] = tensor
    if seen != set(range(53)):
        raise ValueError("Expected exactly 53 official heads")
    return result


def configuration(targets=TARGETS):
    path = project_root() / "docs/model-research-round2/official-mega53.yaml"
    if sha256_file(path) != CONFIG_SHA:
        raise ValueError("Official configuration hash mismatch")
    configuration = yaml.load(path.read_text(encoding="utf-8"), Loader=ConfigLoader)
    labels = configuration["training"]["instruments"]
    if configuration["model"]["num_stems"] != 53 or any(labels[i] != name for i, name in targets.items()):
        raise ValueError("Official target order mismatch")
    return configuration


def folder(extended=False, bowed_strings=False):
    if bowed_strings:
        return project_root() / "data/separation/models/mega53_5head_bowed"
    return project_root() / ("data/separation/models/mega53_5head" if extended else "data/separation/models/mega53_3head")


def prepare(extended=False, bowed_strings=False):
    from .vendor.msst.bs_roformer import BSRoformer
    targets = BOWED_TARGETS if bowed_strings else EXTENDED_TARGETS if extended else TARGETS
    tag = f"mega53-{len(targets)}head"
    target = folder(extended, bowed_strings)
    target.mkdir(parents=True, exist_ok=True)
    folder().mkdir(parents=True, exist_ok=True)
    original = folder() / "official-53.ckpt"
    with FileLock(str(folder() / "prepare.lock"), timeout=0):
        if not original.exists():
            partial = original.with_suffix(".partial")
            request = urllib.request.Request(URL, headers={"User-Agent": "music-analyzer/0.1"})
            with urllib.request.urlopen(request, timeout=60) as response, partial.open("wb") as output:
                total, reported = 0, 0
                for block in iter(lambda: response.read(1024 * 1024), b""):
                    total += len(block)
                    if total > 1400 * 1024 * 1024:
                        raise ValueError("Official checkpoint exceeds size limit")
                    output.write(block)
                    if total - reported >= 128 * 1024 * 1024:
                        print(f"Downloaded {total // (1024 * 1024)} MiB", flush=True)
                        reported = total
            if sha256_file(partial) != CHECKPOINT_SHA:
                raise ValueError("Official checkpoint hash mismatch")
            partial.replace(original)
        if sha256_file(original) != CHECKPOINT_SHA:
            raise ValueError("Official checkpoint hash mismatch")
        config = configuration(targets)
        weights = torch.load(original, map_location="cpu", weights_only=True)
        reduced = prune_heads(weights, tuple(targets))
        config = copy.deepcopy(config)
        config["model"]["num_stems"] = len(targets)
        config["training"]["instruments"] = list(targets.values())
        model = BSRoformer(**config["model"])
        model.load_state_dict(reduced, strict=True)
        checkpoint = target / (tag + ".ckpt")
        temporary = checkpoint.with_suffix(".partial")
        torch.save(reduced, temporary)
        temporary.replace(checkpoint)
        config_path = target / (tag + ".yaml")
        config_path.write_text(yaml.dump(config, Dumper=ConfigDumper, sort_keys=False), encoding="utf-8")
        provenance = {
            "source_url": URL, "source_sha256": CHECKPOINT_SHA, "source_config_sha256": CONFIG_SHA,
            "selected_heads": targets, "transform": "head-pruning-only", "strict_load": True,
            "checkpoint_sha256": sha256_file(checkpoint), "config_sha256": sha256_file(config_path),
            "checkpoint_bytes": checkpoint.stat().st_size,
            "weight_license_evidence": "https://github.com/ZFTurbo/Music-Source-Separation-Training/issues/245",
            "vendor_provenance_sha256": sha256_file(Path(__file__).parent / "vendor/msst/PROVENANCE.json"),
        }
        write_json(target / "provenance.json", provenance)
        print(f"Prepared {checkpoint.stat().st_size / 1024**2:.2f} MiB, strict load passed", flush=True)
        return provenance


def benchmark(audio_path: Path, output: Path, start: float, duration: float, chunk_sec: float, extended=False, bowed_strings=False):
    from .common import read_json
    from .vendor.msst.bs_roformer import BSRoformer
    if start < 0 or duration <= 0 or chunk_sec <= 0:
        raise ValueError("Invalid audio interval or chunk")
    targets = BOWED_TARGETS if bowed_strings else EXTENDED_TARGETS if extended else TARGETS
    tag = f"mega53-{len(targets)}head"
    target = folder(extended, bowed_strings)
    provenance = read_json(target / "provenance.json")
    if sha256_file(folder() / "official-53.ckpt") != CHECKPOINT_SHA or sha256_file(target / (tag + ".ckpt")) != provenance["checkpoint_sha256"]:
        raise ValueError("Checkpoint hash mismatch")
    if sha256_file(target / (tag + ".yaml")) != provenance["config_sha256"]:
        raise ValueError("Derived configuration hash mismatch")
    with sf.SoundFile(audio_path) as source:
        if source.samplerate != 44100 or source.channels != 2:
            raise ValueError("Expected canonical 44100 Hz stereo input")
        source.seek(round(start * 44100))
        audio = source.read(round(duration * 44100), dtype="float32", always_2d=True).T.copy()
    if audio.shape[1] == 0 or not np.isfinite(audio).all():
        raise ValueError("Invalid audio")
    output.mkdir(parents=True, exist_ok=True)
    runtime = project_root() / "data/separation/runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    with FileLock(str(runtime / "gpu-execution.lock"), timeout=0):
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA required")
        torch.manual_seed(0)
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        config = configuration(targets)
        original = BSRoformer(**config["model"])
        weights = torch.load(folder() / "official-53.ckpt", map_location="cpu", weights_only=True)
        if "state_dict" in weights:
            weights = weights["state_dict"]
        if all(k.startswith("module.") for k in weights):
            weights = {k[7:]: v for k, v in weights.items()}
        original.load_state_dict(weights, strict=True)
        del weights
        original.eval().to("cuda")
        probe = torch.from_numpy(audio[:, :min(44100, audio.shape[1])]).unsqueeze(0).to("cuda")
        with torch.inference_mode():
            reference = original(probe, active_stem_ids=list(targets)).cpu().numpy()
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
            amp_reference = original(probe, active_stem_ids=list(targets)).float().cpu().numpy()
        del original
        gc.collect()
        torch.cuda.empty_cache()
        config["model"]["num_stems"] = len(targets)
        loaded = time.perf_counter()
        model = BSRoformer(**config["model"])
        model.load_state_dict(torch.load(target / (tag + ".ckpt"), map_location="cpu", weights_only=True), strict=True)
        model.eval().to("cuda")
        torch.cuda.synchronize()
        load_sec = time.perf_counter() - loaded
        with torch.inference_mode():
            actual = model(probe).cpu().numpy()
        delta = np.abs(reference - actual)
        np.testing.assert_allclose(actual, reference, rtol=1e-4, atol=1e-5)
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
            amp_actual = model(probe).float().cpu().numpy()
        amp_delta = np.abs(amp_reference - amp_actual)
        np.testing.assert_allclose(amp_actual, amp_reference, rtol=1e-3, atol=1e-4)
        print(f"FP32 equivalence passed, max error {delta.max():.3g}", flush=True)
        torch.cuda.reset_peak_memory_stats()
        torch.cuda.synchronize()
        started = time.perf_counter()
        calls = 0
        def infer(piece):
            nonlocal calls
            with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
                result = model(torch.from_numpy(piece).unsqueeze(0).to("cuda"))[0].float().cpu().numpy()
            calls += 1
            print(f"Chunk {calls} completed", flush=True)
            return result
        estimates = overlap_infer(audio, round(chunk_sec * 44100), .5, infer, output_stems=len(targets))
        torch.cuda.synchronize()
        inference_sec = time.perf_counter() - started
        peak_allocated = torch.cuda.max_memory_allocated()
        peak_reserved = torch.cuda.max_memory_reserved()
        tracks = []
        for label, estimate in zip(targets.values(), estimates, strict=True):
            path = output / (label + ".wav")
            sf.write(path, estimate.T, 44100, subtype="FLOAT")
            tracks.append({"label": label, "sha256": sha256_file(path), "rms": float(np.sqrt(np.mean(estimate.astype(np.float64)**2))), "sample_peak": float(np.max(np.abs(estimate)))})
        report = {
            "status": "succeeded", "source_path": str(audio_path.resolve()), "source_sha256": sha256_file(audio_path),
            "start_sec": start, "duration_sec": audio.shape[1] / 44100, "frames": audio.shape[1],
            "gpu": torch.cuda.get_device_name(), "torch": torch.__version__, "chunk_sec": chunk_sec,
            "overlap": .5, "precision": "CUDA AMP FP16", "calls": calls, "load_sec": load_sec,
            "inference_sec": inference_sec, "rtf": inference_sec / (audio.shape[1] / 44100),
            "peak_allocated_bytes": peak_allocated, "peak_reserved_bytes": peak_reserved,
            "memory_scope": "PyTorch allocator, not whole-device memory",
            "equivalence": {"precision": "FP32", "probe_frames": probe.shape[-1], "max_abs": float(delta.max()), "mean_abs": float(delta.mean()), "rtol": 1e-4, "atol": 1e-5},
            "amp_equivalence": {"max_abs": float(amp_delta.max()), "mean_abs": float(amp_delta.mean()), "rtol": 1e-3, "atol": 1e-4},
            "provenance": provenance, "tracks": tracks, "quality_verdict": "Requires ground-truth and listening evaluation",
        }
        write_json(output / "benchmark.json", report)
        print(f"Inference {inference_sec:.2f}s; peak allocated {peak_allocated / 1024**3:.2f} GiB", flush=True)
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--extended", action="store_true", help="Include brass and strings")
    prep.add_argument("--bowed-strings", action="store_true", help="Use bowed_strings instead of broad strings")
    run = sub.add_parser("benchmark")
    run.add_argument("audio", type=Path)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--start", type=float, default=40)
    run.add_argument("--duration", type=float, default=20)
    run.add_argument("--chunk", type=float, default=10)
    run.add_argument("--extended", action="store_true", help="Include brass and strings")
    run.add_argument("--bowed-strings", action="store_true", help="Use bowed_strings instead of broad strings")
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.extended, args.bowed_strings)
    else:
        benchmark(args.audio, args.output, args.start, args.duration, args.chunk, args.extended, args.bowed_strings)


if __name__ == "__main__":
    main()
