from __future__ import annotations

import argparse
import importlib.metadata
import math
import random
import sys
import time
import traceback
from fractions import Fraction
from pathlib import Path

import numpy as np
import soundfile as sf
from filelock import FileLock, Timeout

from .audio import RATE, write_raw_streaming
from .common import read_json, sha256_file, write_json
from .ingest import load_asset
from .job_contracts import JobError, WorkCancelled, job_folder, preset
from .job_service import alive


def run(request_path: Path) -> int:
    request = read_json(request_path)
    root = Path(request["data_root"]).resolve()
    folder = job_folder(root, request["job_id"])
    attempt = Path(request["attempt_dir"]).resolve()
    if (attempt.parent != folder / "attempts" or len(attempt.name) != 34
            or not attempt.name.startswith("a_")
            or any(c not in "0123456789abcdef" for c in attempt.name[2:])
            or request_path.resolve() != attempt / "request.json"):
        raise JobError("REQUEST_PATH", "Invalid worker request path")
    started = time.perf_counter()
    status_path = attempt / "worker.json"
    progress = {"completed": 0, "total": 0}

    def state(value, **details):
        write_json(status_path, {"state": value, "progress": dict(progress), **details})

    def check():
        if (folder / "cancel.request").exists() or not alive(request["owner"]):
            raise WorkCancelled("Cancellation requested or supervisor exited")

    lock = FileLock(str(Path(request["runtime_dir"]) / "gpu-execution.lock"), timeout=0)
    try:
        lock.acquire()
        check()
        state("PREPARING_MODEL")
        import torch
        from demucs.apply import apply_model
        from demucs.pretrained import get_model
        from .environment import inspect_environment
        from .registry import resolve

        if importlib.metadata.version("demucs") != "4.0.1":
            raise JobError("MODEL_VERSION", "Expected Demucs 4.0.1")
        asset = load_asset(root, request["asset_id"])
        selected = preset(request["preset_name"])
        checkpoint, registration = resolve(root, selected.get("model_id", "demucs_htdemucs"))
        env = inspect_environment(attempt / "environment")
        if not env["cuda_available"] or not env["gpu_tensor_test"]["passed"]:
            raise JobError("CUDA_NOT_AVAILABLE", "CUDA GPU is required")
        check()
        if registration.get("engine") in ("melband_roformer", "bs_roformer"):
            from .roformer_runner import run_roformer
            return run_roformer(request, root, attempt, asset, selected, checkpoint, registration, env, started, state, check, progress)
        load_started = time.perf_counter()
        model = get_model(registration["checkpoint_signature"], repo=checkpoint.parent)
        if (model.sources != registration["source_labels"] or model.samplerate != RATE
                or model.audio_channels != 2):
            raise JobError("MODEL_CONTRACT", "Registered output contract mismatch")
        from .demucs_adapter import chunk_count, configure_model, model_members
        trained_segments, resolved_segments = configure_model(model, selected)
        trained_segment = min(trained_segments)
        override = selected["model_segment_override_sec"]
        load_sec = time.perf_counter() - load_started
        random.seed(selected["seed"])
        np.random.seed(selected["seed"])
        torch.manual_seed(selected["seed"])
        torch.cuda.manual_seed_all(selected["seed"])
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        torch.backends.cudnn.enabled = selected["cudnn_enabled"]
        check()
        state("PREPROCESSING")
        audio, _ = sf.read(root / "inputs" / request["asset_id"] / "canonical.wav",
                           dtype="float32", always_2d=True)
        raw = torch.from_numpy(audio.T.copy())
        reference = raw.mean(dim=0)
        mean, scale = reference.mean(), reference.std()
        silent = not np.any(audio)
        normalization_basis = "mono_reference"
        if not silent and float(scale) <= 1e-8:
            scale = raw.std()
            normalization_basis = "channelwise_std_for_cancelling_stereo"
            if float(scale) <= 1e-8:
                raise JobError("CONSTANT_SIGNAL", "Nonzero constant input cannot be normalized")
        stride = int((1 - selected["overlap"]) * int(RATE * selected["segment_sec"]))
        progress["total"] = 0 if silent else chunk_count(
            len(audio), RATE, selected["segment_sec"], selected["overlap"],
            selected["shifts"], len(model_members(model)), selected["seed"])
        state("SEPARATING")
        torch.cuda.reset_peak_memory_stats()
        torch.cuda.synchronize()
        inference_started = time.perf_counter()

        class Deferred:
            def __init__(self, function, args, kwargs):
                self.function, self.args, self.kwargs = function, args, kwargs

            def result(self):
                check()
                value = self.function(*self.args, **self.kwargs)
                torch.cuda.synchronize()
                progress["completed"] += 1
                state("SEPARATING")
                check()
                return value

        class TrackedPool:
            def submit(self, function, *args, **kwargs):
                return Deferred(function, args, kwargs)

        with torch.inference_mode():
            if silent:
                prediction = torch.zeros((len(model.sources), 2, len(audio)), dtype=torch.float32)
            else:
                normalized = (raw - mean) / scale
                prediction = apply_model(
                    model, normalized.unsqueeze(0), device="cuda", shifts=selected["shifts"], split=True,
                    overlap=selected["overlap"], segment=selected["segment_sec"],
                    num_workers=0, pool=TrackedPool(), progress=False)[0]
                prediction.mul_(scale).add_(mean)
                del normalized
        torch.cuda.synchronize()
        inference_sec = time.perf_counter() - inference_started
        memory = {"peak_allocated_bytes": torch.cuda.max_memory_allocated(),
                  "peak_reserved_bytes": torch.cuda.max_memory_reserved(),
                  "measurement": "PyTorch allocator; not whole-device peak"}
        prediction = prediction.cpu().numpy()
        state("VALIDATING_OUTPUT")
        if prediction.shape != (len(model.sources), 2, len(audio)):
            raise JobError("OUTPUT_CONTRACT", "Output shape mismatch")
        for start in range(0, len(audio), RATE * 10):
            check()
            if not np.isfinite(prediction[:, :, start:start + RATE * 10]).all():
                raise JobError("OUTPUT_NONFINITE", "Non-finite model output")
        target = attempt / "result.partial"
        target.mkdir()
        stems = []
        state("EXPORTING")
        for label, estimate in zip(model.sources, prediction, strict=True):
            check()
            path = target / "stems" / (label + ".wav")
            properties = write_raw_streaming(path, estimate.T, check)
            stems.append({"id": "stem_" + label, "family": label,
                          "canonical_id": registration["source_mapping"][label],
                          "path": "stems/" + label + ".wav", "sha256": sha256_file(path),
                          "presence": "unknown", "quality_score": None, **properties})
        squared, peak = 0.0, 0.0
        for start in range(0, len(audio), RATE * 10):
            check()
            error = prediction[:, :, start:start + RATE * 10].astype(np.float64).sum(axis=0).T
            error -= audio[start:start + RATE * 10]
            squared += float(np.square(error).sum())
            peak = max(peak, float(np.abs(error).max()))
        warnings = ["DEV_ONLY: unresolved weight redistribution terms",
                    "No reference stems: perceptual separation quality is not scored",
                    "other remains a residual mixture"]
        warnings.extend(registration.get("quality_notes", []))
        if override is not None:
            warnings.append("Internal model segment shortened: quality may differ from baseline")
        if silent:
            warnings.append("Exactly silent input bypassed model inference")
        demucs_dir = Path(__import__("demucs").__file__).parent
        manifest = {
            "kind": "separation_result", "schema_version": "1.0", "status": "succeeded",
            "job_id": request["job_id"], "asset_id": request["asset_id"],
            "source_sha256": asset["canonical"]["sha256"],
            "original_sha256": asset["input"]["sha256"],
            "timeline": {"sample_rate": RATE, "channels": 2, "num_frames": len(audio), "origin_sec": 0},
            "model": registration, "preset": {**selected, "trained_segment_sec": trained_segment,
                                            "resolved_model_segment_sec": min(resolved_segments),
                                            "member_trained_segments_sec": trained_segments,
                                            "member_resolved_segments_sec": resolved_segments},
            "requested_preset": request["requested_preset"],
            "actual_preset": request["preset_name"],
            "attempt_id": attempt.name, "inference_performed": not silent,
            "environment_lock_sha256": env["environment_lock_sha256"],
            "code_sha256": {name: sha256_file(demucs_dir / name)
                            for name in ("apply.py", "htdemucs.py", "states.py", "audio.py")},
            "worker_sha256": sha256_file(Path(__file__)),
            "pipeline_code_sha256": {name: sha256_file(Path(__file__).parent / name)
                                     for name in ("worker.py", "job_service.py", "job_contracts.py",
                                                  "audio.py", "common.py", "ingest.py", "registry.py", "demucs_adapter.py")},
            "preset_config_sha256": sha256_file(__import__("music_analyzer.job_contracts",
                                                  fromlist=["PRESETS"]).PRESETS),
            "normalization": {"scope": "mixture", "basis": normalization_basis,
                              "mean": float(mean), "std": float(scale),
                              "inverse": "upstream_per_source_std_plus_mean", "per_stem_gain": 1.0},
            "stems": stems, "warnings": warnings,
            "mix_group": {"kind": "estimated_partition", "reconstruction_guaranteed": False},
            "timing": {"model_load_sec": load_sec, "inference_sec": inference_sec,
                       "rtf": inference_sec / (len(audio) / RATE),
                       "wall_sec": time.perf_counter() - started},
            "memory": memory,
            "diagnostics": {"reconstruction_error_rms": math.sqrt(squared / audio.size),
                            "reconstruction_error_peak": peak, "reference_available": False,
                            "raw_sdr": None, "si_sdr": None, "quality_assessment": "not_performed"}}
        check()
        write_json(target / "manifest.json", manifest)
        state("READY_TO_PUBLISH")
        return 0
    except WorkCancelled as error:
        state("CANCELLED", error={"code": "CANCELLED", "message": str(error)})
        return 130
    except Timeout:
        state("FAILED", error={"code": "GPU_BUSY", "message": "Another GPU worker is alive"})
        return 1
    except Exception as error:
        traceback.print_exc()
        # PyTorch supplies a distinct exception type; do not infer OOM from arbitrary messages.
        torch_module = sys.modules.get("torch")
        oom = torch_module is not None and isinstance(error, torch_module.cuda.OutOfMemoryError)
        code = "CUDA_OOM" if oom else getattr(error, "code", "WORKER_ERROR")
        state("FAILED", error={"code": code, "message": str(error)})
        return 12 if oom else 1
    finally:
        lock.release()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(run(args.request))


if __name__ == "__main__":
    main()
