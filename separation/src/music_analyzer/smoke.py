from __future__ import annotations

import importlib.metadata
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import numpy as np
import soundfile as sf
import torch
from demucs.apply import apply_model
from demucs.pretrained import get_model

from . import __version__
from .audio import RATE, make_fixture, write_raw
from .common import project_root, sha256_file, write_json
from .environment import inspect_environment
from .registry import resolve


def run_smoke(data_root: Path, input_path: Path | None = None) -> Path:
    """S1 only: max 60s canonical WAV; new process per invocation; no hidden fallback."""
    if importlib.metadata.version("demucs") != "4.0.1":
        raise RuntimeError("Unsupported Demucs version; expected 4.0.1")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8]
    folder = data_root / "smoke" / run_id
    folder.mkdir(parents=True, exist_ok=False)
    status_path = folder / "status.json"
    events: list[dict] = []
    started = time.perf_counter()

    def state(value: str, **details: object) -> None:
        events.append({"state": value, "elapsed_sec": time.perf_counter() - started})
        write_json(status_path, {"run_id": run_id, "state": value, "events": events, **details})
        print(value, flush=True)

    try:
        state("CREATED")
        state("VALIDATING")
        synthetic = input_path is None
        if input_path is not None:
            if not input_path.is_file() or input_path.suffix.lower() != ".wav":
                raise ValueError("S1 smoke accepts a local WAV only")
            info = sf.info(input_path)
            if info.samplerate != RATE or info.channels not in (1, 2) or not 1 <= info.duration <= 60:
                raise ValueError("S1 smoke requires 44.1kHz mono/stereo WAV, duration 1–60s")
            if input_path.stat().st_size > 32 * 1024 * 1024:
                raise ValueError("S1 input exceeds 32MiB")
        state("PREPARING_MODEL")
        checkpoint, registration = resolve(data_root)
        env = inspect_environment(folder / "environment")
        if not env["cuda_available"] or not env["gpu_tensor_test"]["passed"]:
            raise RuntimeError("CUDA_NOT_AVAILABLE: S1 requires GPU, no automatic CPU fallback")
        model_started = time.perf_counter()
        model = get_model(registration["checkpoint_signature"], repo=checkpoint.parent)
        model.eval()
        if model.sources != registration["source_labels"]:
            raise ValueError("Model output labels differ from registered contract")
        if model.samplerate != RATE or model.audio_channels != 2:
            raise ValueError("Model sample rate/channel contract mismatch")
        model.to("cuda")
        load_sec = time.perf_counter() - model_started
        state("PREPROCESSING")
        if synthetic:
            input_path = make_fixture(folder / "synthetic_input.wav")
        audio, sample_rate = sf.read(input_path, dtype="float32", always_2d=True)
        if not np.isfinite(audio).all():
            raise ValueError("Non-finite input")
        mono_duplicated = audio.shape[1] == 1
        if mono_duplicated:
            audio = np.repeat(audio, 2, axis=1)
        raw_input = torch.from_numpy(audio.T.copy())
        # Mixture-wide Demucs normalization; never per-stem peak normalization.
        reference = raw_input.mean(dim=0)
        mean = reference.mean()
        scale = reference.std()
        if float(scale) <= 1e-8:
            raise ValueError("S1 constant/silent or cancelling-stereo input; silent bypass is scheduled for S2")
        normalized = (raw_input - mean) / scale
        canonical_path = folder / "canonical_input.wav"
        input_properties = write_raw(canonical_path, audio)
        random.seed(0)
        np.random.seed(0)
        torch.manual_seed(0)
        torch.cuda.manual_seed_all(0)
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        preset = {"id": "s1_fp32_4sec", "device": "cuda", "precision": "float32",
                  "segment_sec": 4, "overlap": .25, "shifts": 0, "seed": 0,
                  "batch_size": 1, "num_workers": 0, "split": True,
                  "tf32": False, "fallback": None}
        state("SEPARATING")
        torch.cuda.reset_peak_memory_stats()
        torch.cuda.synchronize()
        inference_started = time.perf_counter()
        with torch.inference_mode():
            prediction = apply_model(model, normalized.unsqueeze(0), device="cuda",
                                     shifts=0, split=True, overlap=.25,
                                     segment=4, num_workers=0, progress=True)[0]
        torch.cuda.synchronize()
        inference_sec = time.perf_counter() - inference_started
        peak_allocated = torch.cuda.max_memory_allocated()
        peak_reserved = torch.cuda.max_memory_reserved()
        prediction = (prediction.cpu() * scale + mean).numpy()
        state("VALIDATING_OUTPUT")
        if prediction.shape != (4, 2, len(audio)) or not np.isfinite(prediction).all():
            raise ValueError("OUTPUT_CONTRACT_MISMATCH")
        temporary = folder / "result.partial"
        temporary.mkdir()
        stems = []
        state("EXPORTING")
        for label, estimate in zip(model.sources, prediction, strict=True):
            path = temporary / "stems" / f"{label}.wav"
            properties = write_raw(path, estimate.T.copy().astype(np.float32))
            stems.append({"id": f"stem_{label}", "family": label,
                          "canonical_id": registration["source_mapping"][label],
                          "path": f"stems/{label}.wav", "sha256": sha256_file(path),
                          "presence": "unknown", "quality_score": None, **properties})
        reconstruction = prediction.sum(axis=0).T - audio
        diagnostics = {
            "reconstruction_error_rms": float(np.sqrt(np.mean(reconstruction.astype(np.float64) ** 2))),
            "reconstruction_error_peak": float(np.abs(reconstruction).max()),
            "raw_sdr": None, "si_sdr": None,
            "reference_available": False,
            "quality_assessment": "not_performed",
        }
        demucs_dir = Path(__import__("demucs").__file__).parent
        code_hashes = {name: sha256_file(demucs_dir / name)
                       for name in ("apply.py", "htdemucs.py", "states.py", "audio.py")}
        manifest = {
            "schema_version": "1.0", "run_id": run_id, "status": "succeeded",
            "pipeline_version": __version__,
            "input": {"sha256": sha256_file(input_path), "synthetic": synthetic,
                      "mono_duplicated": mono_duplicated, "properties": input_properties},
            "timeline": {"sample_rate": RATE, "channels": 2, "num_frames": len(audio), "origin_sec": 0},
            "model": registration,
            "code_sha256": code_hashes,
            "environment_lock_sha256": env["environment_lock_sha256"],
            "runner_sha256": sha256_file(Path(__file__)),
            "taxonomy_version": registration["taxonomy_version"],
            "taxonomy_sha256": sha256_file(project_root() / "separation/configs/instrument_taxonomy.v1.json"),
            "preset": preset,
            "normalization": {"scope": "mixture", "mean": float(mean), "std": float(scale),
                              "inverse": "upstream_per_source_std_plus_mean", "per_stem_gain": 1.0},
            "stems": stems,
            "mix_group": {"id": "main", "kind": "estimated_partition", "reconstruction_guaranteed": False},
            "timing": {"model_load_sec": load_sec, "inference_sec": inference_sec,
                       "rtf": inference_sec / (len(audio) / RATE),
                       "wall_sec": time.perf_counter() - started},
            "memory": {"peak_allocated_bytes": peak_allocated, "peak_reserved_bytes": peak_reserved,
                       "measurement": "PyTorch allocator, includes loaded model; not whole-device peak"},
            "diagnostics": diagnostics,
            "warnings": ["DEV_ONLY: unresolved weight redistribution terms",
                         "S1 smoke verifies execution and raw storage, not music separation quality"],
        }
        write_json(temporary / "manifest.json", manifest)
        temporary.rename(folder / "result")
        state("SUCCEEDED", result="result/manifest.json")
        del model, prediction
        torch.cuda.empty_cache()
        return folder
    except KeyboardInterrupt:
        state("CANCELLED", error="Interrupted by user")
        raise
    except Exception as error:
        state("FAILED", error_type=type(error).__name__, error=str(error))
        raise
