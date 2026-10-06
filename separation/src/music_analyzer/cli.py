from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .common import project_root


def main() -> None:
    # Portable manifests/CLI JSON retain Korean paths on Windows pipes.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="music_analyzer local audio and GPU verification tools")
    parser.add_argument("--data-root", type=Path, default=project_root() / "data/separation")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check-environment")
    prepare_parser = sub.add_parser("prepare-model", help="Explicitly download and pin development model")
    prepare_parser.add_argument("--model", choices=["demucs_htdemucs", "demucs_htdemucs_6s", "demucs_htdemucs_ft", "melband_roformer_kj", "bs_roformer_6s", "melband_karaoke", "bs_karaoke"],
                                default="demucs_htdemucs")
    smoke = sub.add_parser("smoke", help="Run 10s synthetic fixture or short canonical WAV on CUDA")
    smoke.add_argument("--input", type=Path)
    ingest = sub.add_parser("ingest", help="Validate and preserve WAV/FLAC/MP3; create canonical audio asset")
    ingest.add_argument("input", type=Path)
    inspect = sub.add_parser("inspect-asset", help="Verify a published asset's hash and timeline")
    inspect.add_argument("asset_id")

    separate = sub.add_parser("separate", help="Separate a full local song or registered asset on CUDA")
    source = separate.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path)
    source.add_argument("--asset-id")
    separate.add_argument("--preset", choices=["baseline", "memory_safe", "quality", "quality_6s", "quality_ft", "vocal_roformer", "instrument_roformer_6s", "karaoke_roformer", "bs_karaoke"], default="baseline")
    for name in ("job-status", "cancel-job", "retry-job", "inspect-result"):
        command = sub.add_parser(name)
        command.add_argument("job_id")
    compare = sub.add_parser("compare-results", help="Create a local listening comparison of the same song")
    compare.add_argument("--job-id", nargs="+", required=True)
    compare.add_argument("--window", action="append", help="start_seconds:duration_seconds, repeatable")
    pipeline = sub.add_parser("separate-pipeline", help="Selected RoFormer vocals then experimental instruments from accompaniment")
    pipeline_source = pipeline.add_mutually_exclusive_group(required=True)
    pipeline_source.add_argument("--input", type=Path)
    pipeline_source.add_argument("--vocal-job-id")
    refine_parser = sub.add_parser("refine-guitar-other")
    refine_parser.add_argument("--job-id", required=True)
    refine_parser.add_argument("--window", action="append", default=None)
    sub.add_parser("recover-jobs")
    args = parser.parse_args()
    data_root = args.data_root.resolve()

    if args.command == "refine-guitar-other":
        from .pair_refinement import refine, compare
        windows = [tuple(map(float,value.split(":"))) for value in args.window] if args.window else [(0,20)]
        folder = refine(data_root,args.job_id)
        preview = compare(data_root,folder,windows)
        print(json.dumps({"refinement_dir":str(folder),"comparison_dir":str(preview),"page":str(preview/"comparison.html")},indent=2))
        return
    if args.command == "separate-pipeline":
        from .pipeline import run_pipeline
        folder = run_pipeline(data_root, args.input, args.vocal_job_id, lambda job: print(json.dumps({"job_id":job["job_id"],"state":job["state"],"progress":job.get("progress")}),file=sys.stderr,flush=True))
        print(json.dumps({"pipeline_dir":str(folder),"manifest":str(folder/"manifest.json")},indent=2))
        return
    if args.command == "compare-results":
        from .comparison import compare_results
        from .job_contracts import JobError
        try:
            windows = [tuple(map(float, value.split(":"))) for value in args.window] if args.window else None
            if windows and any(len(window) != 2 for window in windows):
                raise ValueError("Each window must be start_seconds:duration_seconds")
            folder = compare_results(data_root, args.job_id, windows)
        except (JobError, ValueError, OSError) as error:
            print(json.dumps({"error": {"code": getattr(error, "code", "COMPARISON_ERROR"), "message": str(error)}},
                             ensure_ascii=False), file=sys.stderr)
            raise SystemExit(2) from None
        print(json.dumps({"comparison_dir": str(folder), "page": str(folder / "comparison.html")},
                         ensure_ascii=False, indent=2))
        return
    if args.command in ("separate", "job-status", "cancel-job", "retry-job", "recover-jobs", "inspect-result"):
        from .ingest import AudioInputError, ingest_file
        from .job_service import JobService
        from .job_contracts import JobError, job_folder, verify_result
        service = JobService(data_root)
        last = None

        def update(job):
            nonlocal last
            progress = job.get("progress") or {}
            marker = (job["state"], progress.get("completed", 0) // 10)
            if marker != last:
                print(json.dumps({"job_id": job["job_id"], "state": job["state"],
                                  "progress": progress}, ensure_ascii=False), file=sys.stderr, flush=True)
                last = marker

        try:
            if args.command == "separate":
                asset_id = args.asset_id or ingest_file(args.input, data_root).name
                result = service.run(asset_id, args.preset, update)
            elif args.command == "job-status":
                result = service.status(args.job_id)
            elif args.command == "cancel-job":
                result = service.cancel(args.job_id)
            elif args.command == "retry-job":
                result = service.retry(args.job_id, update)
            elif args.command == "recover-jobs":
                result = {"recovered": service.recover()}
            else:
                result = verify_result(job_folder(data_root, args.job_id) / "result", service.status(args.job_id))
        except (JobError, AudioInputError, OSError) as error:
            print(json.dumps({"error": {"code": getattr(error, "code", "IO_ERROR"), "message": str(error)}},
                             ensure_ascii=False), file=sys.stderr)
            raise SystemExit(2) from None
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.command in ("separate", "retry-job") and result["state"] != "SUCCEEDED":
            raise SystemExit(130 if result["state"] == "CANCELLED" else 1)
        return
    if args.command in ("ingest", "inspect-asset"):
        from .ingest import AudioInputError, ingest_file, load_asset
        try:
            if args.command == "ingest":
                folder = ingest_file(args.input, data_root)
                manifest = load_asset(data_root, folder.name)
                result = {"asset_id": manifest["asset_id"], "asset_dir": str(folder),
                          "canonical_path": str(folder / "canonical.wav"), "manifest": manifest}
            else:
                result = load_asset(data_root, args.asset_id)
        except AudioInputError as error:
            print(json.dumps({"error": {"code": error.code, "message": str(error)}},
                             ensure_ascii=False), file=sys.stderr)
            raise SystemExit(2) from None
        except OSError as error:
            print(json.dumps({"error": {"code": "IO_ERROR", "message": str(error)}},
                             ensure_ascii=False), file=sys.stderr)
            raise SystemExit(2) from None
    elif args.command == "check-environment":
        from .environment import inspect_environment
        result = inspect_environment(data_root / "environment")
    elif args.command == "prepare-model":
        from .registry import prepare
        result = prepare(data_root, args.model)
    else:
        from .smoke import run_smoke
        result = {"run_dir": str(run_smoke(data_root, args.input))}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
