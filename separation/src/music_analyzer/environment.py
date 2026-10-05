from __future__ import annotations

import importlib.metadata
import platform
import subprocess
import sys
from pathlib import Path

import psutil
import torch

from .common import sha256_file, write_json


def command(args: list[str]) -> str:
    try:
        return subprocess.run(args, check=True, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError) as error:
        return f"UNAVAILABLE: {type(error).__name__}: {error}"


def inspect_environment(report_dir: Path) -> dict:
    report_dir.mkdir(parents=True, exist_ok=True)
    freeze = command([sys.executable, "-m", "pip", "freeze"])
    lock = report_dir / "environment.freeze.txt"
    lock.write_text(freeze + "\n", encoding="utf-8")
    report = {
        "python": sys.version,
        "platform": platform.platform(),
        "packages": {name: importlib.metadata.version(name)
                     for name in ("torch", "torchaudio", "demucs", "numpy", "soundfile")},
        "environment_lock_sha256": sha256_file(lock),
        "cuda_runtime": torch.version.cuda,
        "cuda_available": torch.cuda.is_available(),
        "host_ram_bytes": psutil.virtual_memory().total,
        "nvidia_smi": command(["nvidia-smi", "--query-gpu=name,memory.total,memory.free,driver_version",
                               "--format=csv,noheader"]),
        "ffmpeg": command(["ffmpeg", "-version"]).splitlines()[0],
        "ffprobe": command(["ffprobe", "-version"]).splitlines()[0],
        "gpu_tensor_test": None,
    }
    if torch.cuda.is_available():
        with torch.inference_mode():
            test = torch.ones((256, 256), device="cuda")
            result = test @ test
            torch.cuda.synchronize()
            report["gpu_tensor_test"] = {
                "passed": bool(torch.all(result == 256).item()),
                "device": torch.cuda.get_device_name(),
            }
        del test, result
        torch.cuda.empty_cache()
    write_json(report_dir / "environment.json", report)
    return report
