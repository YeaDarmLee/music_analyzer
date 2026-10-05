from __future__ import annotations

import html
import json
import math
import shutil
from pathlib import Path
from uuid import uuid4

import numpy as np
import soundfile as sf

from .audio import RATE
from .common import read_json, sha256_file, write_json
from .ingest import load_asset
from .job_contracts import JobError, job_folder, verify_result

LABELS = {"baseline": ("기존 4트랙", "기존 4초 구간·25% 겹침·1회 추론 결과입니다."),
          "quality": ("구간 개선 4트랙", "같은 모델에서 전체 7.8초 문맥·50% 겹침·두 위치의 추론 평균을 사용했습니다."),
          "quality_ft": ("추가 학습 4트랙", "악기별 추가 학습 모델에 7.8초 문맥·50% 겹침·두 위치 추론 평균을 적용했습니다."),
          "quality_6s": ("기타·피아노 포함 6트랙", "원곡에서 여섯 트랙을 직접 추출했습니다. 피아노는 실험적 결과입니다. 이 결과의 other는 기타·피아노를 제외하므로 4트랙 other와 같은 파트가 아닙니다.")}


LABELS["vocal_roformer"] = ("RoFormer 보컬·반주", "보컬 전용 모델입니다. 모든 모델의 전체 반주는 원본에서 추정 보컬을 뺀 결과로 비교합니다. 개별 악기 분리는 아닙니다.")


LABELS["instrument_roformer_6s"] = ("BS-RoFormer 악기 후보", "같은 RoFormer 반주를 입력으로 받은 6악기 후보입니다. 보컬은 잔여 보컬 진단용이며 확정 보컬을 대체하지 않습니다. 학습 내역과 품질은 미확인입니다.")


def compare_results(root: Path, job_ids: list[str],
                    windows: list[tuple[float, float]] | None = None) -> Path:
    if not 2 <= len(job_ids) <= 8 or len(set(job_ids)) != len(job_ids):
        raise JobError("COMPARISON_JOBS", "Select 2–8 distinct successful jobs")
    manifests, jobs = [], []
    for job_id in job_ids:
        folder = job_folder(root, job_id)
        job = read_json(folder / "job.json")
        if job["state"] != "SUCCEEDED":
            raise JobError("COMPARISON_STATE", "Only successful jobs can be compared")
        manifests.append(verify_result(folder / "result", job))
        jobs.append(job)
    if len({(m["source_sha256"], m["timeline"]["num_frames"]) for m in manifests}) != 1:
        raise JobError("COMPARISON_INPUT", "Results must use the same canonical input and timeline")
    asset = load_asset(root, jobs[0]["asset_id"])
    frames = asset["timeline"]["num_frames"]
    if frames != manifests[0]["timeline"]["num_frames"] or asset["canonical"]["sha256"] != manifests[0]["source_sha256"]:
        raise JobError("COMPARISON_INPUT", "Registered input differs from the result")
    windows = windows or [(20, 20), (70, 20), (135, 20)]
    if not 1 <= len(windows) <= 10:
        raise JobError("COMPARISON_WINDOW", "Select 1–10 windows")
    for start, duration in windows:
        if not math.isfinite(start) or not math.isfinite(duration) or start < 0 or duration <= 0 or duration > 60:
            raise JobError("COMPARISON_WINDOW", "Invalid comparison window")
        if round((start + duration) * RATE) > frames:
            raise JobError("COMPARISON_WINDOW", "Comparison window exceeds the song")
    maximum = max([asset["canonical"]["peak"]] +
                  [s["peak"] for m in manifests for s in m["stems"]])
    maximum = max(maximum, max(asset["canonical"]["peak"] + next(s["peak"] for s in m["stems"] if s["family"] == "vocals") for m in manifests))
    gain = min(1., .9 / maximum) if maximum else 1.
    identifier = "compare_" + uuid4().hex
    parent = root / "comparisons"
    parent.mkdir(parents=True, exist_ok=True)
    partial = parent / ("." + identifier + ".partial")
    partial.mkdir()
    try:
        (partial / "clips").mkdir()
        variants = []
        sources = {"original": root / "inputs" / jobs[0]["asset_id"] / "canonical.wav"}
        for index, (job, manifest) in enumerate(zip(jobs, manifests, strict=True)):
            key = "v" + str(index)
            name, description = LABELS.get(job["requested_preset"], (job["requested_preset"], "등록된 분리 결과"))
            variants.append({"key": key, "label": name, "description": description,
                             "job_id": job["job_id"], "stems": [s["family"] for s in manifest["stems"]],
                             "raw_manifest_sha256": sha256_file(job_folder(root, job["job_id"]) / "result/manifest.json")})
            for stem in manifest["stems"]:
                sources[key + "_" + stem["family"]] = job_folder(root, job["job_id"]) / "result" / stem["path"]
            if "instrumental" not in variants[-1]["stems"]:
                variants[-1]["stems"].append("instrumental")
                variants[-1]["derived_instrumental"] = "input_minus_estimated_vocals"
                sources[key + "_instrumental"] = (sources["original"], sources[key + "_vocals"])
        estimated_bytes = len(sources) * sum(round(duration * RATE) for _, duration in windows) * 2 * 2
        if shutil.disk_usage(parent).free < estimated_bytes + 1024 ** 3:
            raise JobError("DISK_SPACE", "Insufficient space for comparison files and 1GiB reserve")
        rendered_windows = []
        for index, (start, duration) in enumerate(windows):
            start_frame, count = round(start * RATE), round(duration * RATE)
            files, measurements = {}, {}
            for key, path in sources.items():
                def read_clip(filename):
                    with sf.SoundFile(filename) as source:
                        source.seek(start_frame)
                        return source.read(count, dtype="float32", always_2d=True)
                audio = read_clip(path[0]) - read_clip(path[1]) if isinstance(path, tuple) else read_clip(path)
                if len(audio) != count:
                    raise JobError("COMPARISON_READ", "Source clip was truncated")
                rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
                preview = (audio * np.float32(gain)).astype(np.float32)
                if float(np.abs(preview).max()) > .90001:
                    raise JobError("COMPARISON_PEAK", "Manifest peak differs from actual samples")
                filename = f"clips/w{index}_{key}.wav"
                sf.write(partial / filename, preview, RATE, subtype="PCM_16")
                decoded, _ = sf.read(partial / filename, dtype="float32", always_2d=True)
                if not np.allclose(decoded, preview, rtol=0, atol=1 / 32768 + 1e-7):
                    raise JobError("COMPARISON_QUANTIZATION", "Preview PCM16 conversion failed")
                files[key] = filename
                measurements[key] = {"raw_rms": rms, "raw_rms_dbfs": 20 * math.log10(rms) if rms else None,
                                     "preview_sha256": sha256_file(partial / filename),
                                     "num_frames": len(decoded)}
            def stamp(seconds):
                return f"{int(seconds) // 60}:{int(seconds) % 60:02d}"
            rendered_windows.append({"start_sec": start, "duration_sec": duration,
                                     "label": stamp(start) + "–" + stamp(start + duration),
                                     "files": files, "measurements": measurements})
        data = {"schema_version": "1.0", "kind": "listening_comparison", "comparison_id": identifier,
                "original_name": asset["input"]["original_name"], "source_sha256": asset["canonical"]["sha256"],
                "preview": {"format": "WAV/PCM16", "sample_rate": RATE, "channels": 2,
                            "common_gain": gain, "gain_scope": "all_variants_all_stems_all_windows",
                            "dynamic_gain": False, "denoise": False},
                "variants": variants, "windows": rendered_windows,
                "assessment": {"reference_stems_available": False, "quality_improvement_verified": False}}
        template = Path(__file__).with_name("comparison.html").read_text(encoding="utf-8")
        embedded = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
        page = template.replace("__DATA__", embedded).replace("__SONG__", html.escape(data["original_name"]))
        page = page.replace("__GAIN__", f"{gain:.6f}")
        if asset["input"]["original_name"] == "instrumental.wav":
            page = page.replace("원곡", "입력 반주").replace("입력 반주과", "입력 반주와")
            page = page.replace('vocals:"보컬"', 'vocals:"보컬 잔여물"')
            page = page.replace("instrumental.wav ·", "보컬 제거 반주의 악기 분리 비교 ·")
        (partial / "comparison.html").write_text(page, encoding="utf-8")
        write_json(partial / "manifest.json", data)
        partial.rename(parent / identifier)
        return parent / identifier

    except BaseException:
        resolved = partial.resolve()
        if resolved.is_relative_to(parent.resolve()) and partial.is_dir() and not partial.is_symlink():
            shutil.rmtree(partial)
        raise
