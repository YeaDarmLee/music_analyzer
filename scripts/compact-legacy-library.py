"""Legacy compaction: keep every existing analysis, drop only its intermediates.

For each analysis in a library the script first VALIDATES it; anything uncertain is SKIPPED (left untouched):
  state SUCCEEDED | stem set equals the contract for its (model, separation_version) | original exists | every WAV opens, is 44.1 kHz stereo
  with the same frame count as the original, duration matches the record | no NaN/Inf | recorded sha256 (when present) matches the file
  | partition sum <= 2e-6 where the pipeline guarantees it | no final file / job / asset is also used by another analysis | no analysis is running.
Compaction = lifecycle.finalize(): final stems -> web/<id>/final/, canonical original -> web/<id>/original.wav, manifest.json written,
then jobs results, evidence, routing scratch and intermediate/duplicate assets are removed. Dry run by default.
usage: compact-legacy-library.py [--root data/separation] [--apply] [--only analysis_id] [--json OUT]
"""
import argparse, hashlib, json, re, sys, time
from pathlib import Path
import numpy as np, soundfile as sf
from music_analyzer import lifecycle
from music_analyzer.common import project_root, read_json, write_json

BASE11 = {"lead", "backing", "piano", "synth", "strings", "brass", "acoustic_guitar", "guitar", "bass", "drums", "other"}
CONTRACTS = {  # (model, separation_version) -> stems; anything else is SKIPPED
    ("basic_2", None): {"vocals", "instrumental"},
    ("basic_6", None): {"vocals", "piano", "guitar", "bass", "drums", "other"},
    ("bs_karaoke", None): {"lead", "backing"},
    ("final_10", "instrumental-with-brass-v5"): BASE11,
    ("final_11", "instrumental-with-brass-recovery-v7"): BASE11,
    **{("final_11", v): BASE11 | {"guitar_residual"} for v in ("staged-guitar-residual-v8", "staged-guitar-residual-v9", "staged-guitar-residual-v10")},
    **{("final_11", v): BASE11 | {"guitar_residual", "percussion"} for v in (
        "staged-context-percussion-v11", "staged-context-percussion-v12", "staged-context-strings-v13", "staged-context-backing-v14",
        "staged-context-families-v15", "staged-context-pads-v16")},
}
PARTITION_GUARANTEED_MODELS = ("basic_2", "basic_6", "final_11")
RATE = 44100


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 22), b""):
            digest.update(block)
    return digest.hexdigest()


def validate(root, record, others_text):
    """Returns (problems, info). Empty problems = safe to compact."""
    problems, info = [], {}
    if record.get("state") != "SUCCEEDED":
        return [f"state is {record.get('state')}"], info
    contract = CONTRACTS.get((record.get("model"), record.get("separation_version")))
    if contract is None:
        return [f"no stem contract for ({record.get('model')}, {record.get('separation_version')})"], info
    tracks = record.get("tracks", [])
    families = [t.get("family") for t in tracks]
    if sorted(families) != sorted(contract):
        problems.append(f"stems {sorted(families)} != contract {sorted(contract)}")
    original = root / record["original"] if record.get("original") else None
    if original is None or not original.is_file():
        return problems + ["original missing"], info
    try:
        reference = sf.info(original)
    except RuntimeError as error:
        return problems + [f"original unreadable: {error}"], info
    if reference.samplerate != RATE or reference.channels != 2:
        problems.append(f"original is {reference.samplerate} Hz x{reference.channels}")
    duration = reference.frames / reference.samplerate
    if not 1 <= duration <= 900 or abs(duration - float(record.get("duration", duration))) > .05:
        problems.append(f"duration {duration:.3f}s vs record {record.get('duration')}")
    for track in tracks:
        path = root / track["path"]
        if not path.is_file():
            problems.append(f"{track['family']}: file missing")
            continue
        try:
            meta = sf.info(path)
        except RuntimeError as error:
            problems.append(f"{track['family']}: unreadable ({error})")
            continue
        if (meta.samplerate, meta.channels, meta.frames) != (reference.samplerate, 2, reference.frames):
            problems.append(f"{track['family']}: format {meta.samplerate}/{meta.channels}/{meta.frames}")
        if track.get("sha256") and sha256(path) != track["sha256"]:
            problems.append(f"{track['family']}: sha256 differs from the record")
        # another analysis using the same file, job or asset => never move it
        for token in {str(track["path"]).replace(chr(92), "/"), *lifecycle.ids_in(str(track["path"]))}:
            if token in others_text:
                problems.append(f"{track['family']}: shared with another analysis ({token[-40:]})")
                break
    if problems:
        return problems, info
    # one decode pass: finite check and partition error against the original
    handles = {t["family"]: sf.SoundFile(root / t["path"]) for t in tracks}
    maximum = 0.
    try:
        with sf.SoundFile(original) as source:
            for block in source.blocks(blocksize=RATE * 10, dtype="float64", always_2d=True):
                total = np.zeros_like(block)
                for family, handle in handles.items():
                    piece = handle.read(len(block), dtype="float64", always_2d=True)
                    if not np.isfinite(piece).all():
                        problems.append(f"{family}: NaN/Inf")
                    total += piece
                if not np.isfinite(block).all():
                    problems.append("original: NaN/Inf")
                maximum = max(maximum, float(np.max(np.abs(total - block))))
    finally:
        for handle in handles.values():
            handle.close()
    info["partition_max_abs_error"] = maximum
    if record["model"] in PARTITION_GUARANTEED_MODELS and maximum > 2e-6:
        problems.append(f"partition error {maximum:.2e} > 2e-6")
    return list(dict.fromkeys(problems)), info


def verify_promoted(root, expected):
    """after_promote hook: every promoted file exists with the size measured before the move."""
    def check(record):
        errors = []
        for track in record["tracks"]:
            path = root / track["path"]
            if not path.is_file() or path.stat().st_size != expected.get(track["family"]):
                errors.append(f"{track['family']}: promoted file differs")
        if not (root / record["original"]).is_file():
            errors.append("original missing after promotion")
        if not (root / "web" / record["id"] / "manifest.json").is_file():
            errors.append("manifest missing")
        return errors
    return check


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(project_root() / "data/separation")); ap.add_argument("--apply", action="store_true")
    ap.add_argument("--only"); ap.add_argument("--json")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    records = {}
    for path in (root / "web").glob("analysis_*/record.json"):
        records[path.parent.name] = (path, read_json(path))
    if any(r.get("state") in ("QUEUED", "RUNNING") for _, r in records.values()):
        sys.exit("an analysis is running; try again when the library is idle")
    texts = {name: path.read_text(encoding="utf-8", errors="replace") for name, (path, _) in records.items()}
    results, freed_total = [], 0
    for name, (path, record) in sorted(records.items(), key=lambda kv: str(kv[1][1].get("created"))):
        if args.only and name != args.only:
            continue
        if (root / "web" / name / "manifest.json").exists() and "storage" in record:
            results.append({"id": name, "name": record.get("name"), "action": "ALREADY", "freed_bytes": 0}); continue
        others = "\n".join(t for n, t in texts.items() if n != name).replace("\\\\", "/")
        started = time.monotonic()
        problems, info = validate(root, record, others)
        if problems:
            results.append({"id": name, "name": record.get("name"), "model": record.get("model"), "action": "SKIP", "problems": problems})
            print("SKIP ", name[-8:], record.get("name"), "|", "; ".join(problems)[:200], flush=True); continue
        dry = lifecycle.finalize(root, json.loads(json.dumps(record)), True, dry_run=True)
        entry = {"id": name, "name": record.get("name"), "model": record.get("model"), "version": record.get("separation_version"),
                 "action": "COMPACT" if args.apply else "WOULD-COMPACT", "estimated_freed_bytes": dry["freed_bytes"],
                 "estimated_files": dry["removed_files"], "partition_max_abs_error": info.get("partition_max_abs_error"),
                 "validate_seconds": round(time.monotonic() - started, 1)}
        if args.apply:
            sizes = {t["family"]: (root / t["path"]).stat().st_size for t in record["tracks"]}
            row = json.loads(json.dumps(record))
            result = lifecycle.finalize(root, row, True, after_promote=verify_promoted(root, sizes))
            if result["mode"] == "removed":
                row["storage"] = {**result, "compacted_legacy": True}
                write_json(path, row)
                entry.update(freed_bytes=result["freed_bytes"], removed_files=result["removed_files"], errors=result["errors"])
                freed_total += result["freed_bytes"]
            else:
                write_json(path, row)   # files may be promoted already; the record must follow them
                entry.update(action="FAILED-VERIFY", errors=result["errors"])
        results.append(entry)
        print(entry["action"], name[-8:], record.get("name"), f"{entry['estimated_freed_bytes'] / 2**30:.2f} GB", flush=True)
    summary = {"compact": sum(r["action"] in ("COMPACT", "WOULD-COMPACT") for r in results), "skip": sum(r["action"] == "SKIP" for r in results),
               "already": sum(r["action"] == "ALREADY" for r in results), "failed_verify": sum(r["action"] == "FAILED-VERIFY" for r in results),
               "estimated_freed_gb": round(sum(r.get("estimated_freed_bytes", 0) for r in results) / 2**30, 2),
               "freed_gb": round(freed_total / 2**30, 2)}
    print(json.dumps(summary))
    if args.json:
        write_json(Path(args.json), {"summary": summary, "analyses": results})


main()
