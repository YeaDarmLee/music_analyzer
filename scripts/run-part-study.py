"""Prepare and run an owner-scoped short musical-part comparison. No default preset changes."""
from pathlib import Path
import argparse
import subprocess
from uuid import uuid4

import soundfile as sf

from music_analyzer.audio import RATE, write_raw
from music_analyzer.auth import AuthStore
from music_analyzer.common import project_root, read_json, write_json, sha256_file
from music_analyzer.part_study import synth_controls


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis-id", required=True)
    parser.add_argument("--member-name", required=True)
    parser.add_argument("--window", action="append", default=None, help="start:duration; 1..30 seconds")
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    store = AuthStore()
    users = store.query("SELECT id FROM users WHERE display_name=%s", (args.member_name,))
    if len(users) != 1 or not store.owns(users[0]["id"], args.analysis_id):
        parser.error("Choose exactly one member and that member's own analysis.")
    import re
    if not re.fullmatch(r"analysis_[0-9a-f]{32}", args.analysis_id): parser.error("Invalid analysis ID")
    root = project_root() / "data/separation"
    record = read_json(root / "web" / args.analysis_id / "record.json")
    if record["state"] != "SUCCEEDED": parser.error("A completed analysis is required")
    windows = [tuple(map(float, value.split(":"))) for value in (args.window or ["40:20", "100:20"])]
    if any(len(w) != 2 or w[0] < 0 or not 1 <= w[1] <= 30 or w[0]+w[1] > record["duration"] for w in windows): parser.error("Invalid short window")
    study = project_root() / "data/part-studies" / ("study_" + uuid4().hex)
    study.mkdir(parents=True)
    def clip(relative, output, start, duration):
        source = (root / relative).resolve()
        if not source.is_relative_to(root.resolve()): raise ValueError("Unsafe source")
        digest = sha256_file(source)
        with sf.SoundFile(source) as audio:
            if audio.samplerate != RATE or audio.channels != 2: raise ValueError("Canonical stereo required")
            audio.seek(round(start * RATE)); value = audio.read(round(duration * RATE), dtype="float32", always_2d=True)
        if len(value) != round(duration * RATE) or digest != sha256_file(source): raise ValueError("Invalid or changed source")
        write_raw(output, value)
        return digest
    cases = []
    for start, duration in windows:
        for family in ("guitar", "other"):
            parent = next(t for t in record["tracks"] if t["family"] == family)
            name = f"orange_{int(start):03d}_{family}"
            out = study / name; out.mkdir()
            input_path = out / "parent.wav"
            parent_hash = clip(parent["path"], input_path, start, duration)
            clip(record["original"], out / "original.wav", start, duration)
            existing = ("lead_guitar", "guitar_residual") if family == "guitar" else ("synth_pad", "other_residual")
            for index, label in enumerate(existing):
                track = next((t for t in record["tracks"] if t["family"] == label), None)
                if track: clip(track["path"], out / ("current_" + str(index+1) + ".wav"), start, duration)
            cases.append({"name": name, "family": family, "input": str(input_path), "input_sha256": sha256_file(input_path),
                          "output": str(out), "original_start_sec": start, "duration_sec": duration,
                          "source_analysis_id": args.analysis_id, "parent_sha256": parent_hash, "ground_truth_available": False})
    cases += synth_controls(study / "controls")
    for case in cases:
        case.setdefault("output", str(study / case["name"]))
        case.setdefault("input_sha256", sha256_file(Path(case["input"])))
    plan = {"study_id": study.name, "owner_user_id": users[0]["id"], "source_analysis_id": args.analysis_id,
            "source_name": record["name"], "data_root": str(root), "cases": cases,
            "quality_improvement_verified": False, "scope": "short comparison; not default engine"}
    write_json(study / "plan.json", plan)
    print("PLAN", study / "plan.json", flush=True)
    if not args.prepare_only:
        python = root / "tools/clapsep-env/Scripts/python.exe"
        log = study / "worker.log"
        with log.open("w", encoding="utf-8") as handle:
            result = subprocess.run([str(python), "-m", "music_analyzer.part_study", "--infer-plan", str(study / "plan.json")],
                                    cwd=project_root(), stdout=handle, stderr=subprocess.STDOUT)
        print("Worker exit", result.returncode, "log", log, flush=True)
        if result.returncode: raise SystemExit(result.returncode)


if __name__ == "__main__": main()
