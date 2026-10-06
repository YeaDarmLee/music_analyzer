"""Publish completed real-song comparisons to the original owner's library only."""
from pathlib import Path
import argparse
import shutil
import time
from uuid import uuid4

import soundfile as sf

from music_analyzer.auth import AuthStore
from music_analyzer.common import project_root, read_json, write_json, sha256_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    args = parser.parse_args()
    plan = read_json(args.plan)
    root = project_root() / "data/separation"
    study_root = (project_root() / "data/part-studies").resolve()
    if not args.plan.resolve().is_relative_to(study_root): parser.error("Plan must belong to local part-studies")
    store = AuthStore()
    if not store.owns(plan["owner_user_id"], plan["source_analysis_id"]): parser.error("Source ownership changed; not publishing")
    report = []
    for case in plan["cases"]:
        out = Path(case["output"]).resolve()
        if not out.is_relative_to(study_root): raise ValueError("Study output escapes its root")
        manifest = read_json(out / "manifest.json")
        if manifest["state"] != "CANDIDATE_READY" or not manifest["model_inference_performed"]: raise ValueError("Completed inference required")
        report.append({"name": case["name"], "metrics": manifest["metrics"], "results": manifest["results"]})
        if not case.get("source_analysis_id"): continue
        if manifest.get("published_analysis_id"):
            if not store.owns(plan["owner_user_id"], manifest["published_analysis_id"]): raise ValueError("Published ownership mismatch")
            print("EXISTING", manifest["published_analysis_id"], flush=True); continue
        identifier = "analysis_" + uuid4().hex
        folder = root / "web" / identifier; folder.mkdir(parents=True)
        labels = ["리드 기타", "리듬 기타"] if case["family"] == "guitar" else ["지속 코드 패드", "신스 아르페지오"]
        specification = [("current_1", "기존 전체 곡 · 목표 추출"), ("current_2", "기존 전체 곡 · 잔여"),
                         ("baseline", "구간 재실행 · 기존 프롬프트"), ("baseline_residual", "구간 재실행 · 잔여"),
                         ("part_a", "독립 추출 A · " + labels[0]), ("part_b", "독립 추출 B · " + labels[1]),
                         ("unassigned", "미배정 차이 신호 · 악기 파트 아님")]
        tracks = []
        for filename, label in specification:
            source = out / (filename + ".wav")
            if not source.is_file(): continue
            with sf.SoundFile(source) as audio:
                if audio.samplerate != 44100 or audio.channels != 2 or audio.frames != manifest["timeline"]["num_frames"]: raise ValueError("Study timeline mismatch")
            if filename in manifest["results"] and sha256_file(source) != manifest["results"][filename]["sha256"]: raise ValueError("Estimate changed")
            destination = folder / source.name; shutil.copyfile(source, destination)
            tracks.append({"family": "study_" + filename, "display_name": label, "path": str(destination.relative_to(root)), "sha256": sha256_file(destination)})
        shutil.copyfile(out / "input.wav", folder / "parent.wav")
        start = int(case["original_start_sec"]); end = start + int(case["duration_sec"])
        title = "기타" if case["family"] == "guitar" else "other·신스"
        row = {"id": identifier, "name": f"Orange · {title} 비교 · {start//60}:{start%60:02d}–{end//60}:{end%60:02d}",
               "state": "SUCCEEDED", "stage": "실험 후보 생성 · 청취 평가 필요", "progress": 100,
               "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "duration": case["duration_sec"],
               "model": "part_study", "kind": "part_comparison", "original": str((folder / "parent.wav").relative_to(root)),
               "tracks": tracks, "job_ids": [], "source_analysis_id": plan["source_analysis_id"],
               "study_id": plan["study_id"], "quality_improvement_verified": False, "study_metrics": manifest["metrics"]}
        write_json(folder / "record.json", row)
        store.assign(plan["owner_user_id"], identifier)
        manifest["published_analysis_id"] = identifier; write_json(out / "manifest.json", manifest)
        print("PUBLISHED", identifier, title, start, flush=True)
    write_json(args.plan.parent / "report.json", {"study_id": plan["study_id"], "source_analysis_id": plan["source_analysis_id"], "cases": report,
                "quality_improvement_verified": False, "sam_audio": "Not executed: gated checkpoints require user-approved access and separate dependencies."})


if __name__ == "__main__": main()
