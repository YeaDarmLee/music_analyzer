"""A/B listening folders: data/commercial-eval/listening/case_XXX/{original.wav,baseline/,commercial/,comparison.json}.
Same sample rate / length / gain (raw pipeline output, no normalization); verified before copying."""
import shutil
import soundfile as sf
from music_analyzer.common import project_root, read_json, write_json

base = project_root() / "data/commercial-eval"; out = base / "listening"
for i, name in enumerate(("pad00-mix", "pad01-mix", "pad02-mix", "pad03-mix")):
    b, c = base / "pad-baseline" / name, base / "pad" / name
    if not (b / "report.json").exists() or not (c / "report.json").exists():
        continue
    case = out / f"case_{i:03d}_{name}"; (case / "baseline").mkdir(parents=True, exist_ok=True); (case / "commercial").mkdir(exist_ok=True)
    mix = read_json(c / "prepared.json")["input"]; shutil.copyfile(mix, case / "original.wav")
    info = sf.info(case / "original.wav"); summary = {"case": name, "frames": info.frames, "samplerate": info.samplerate, "stems": {}}
    for side, folder in (("baseline", b), ("commercial", c)):
        for wav in sorted((folder / "evaluation-outputs").glob("*.wav")):
            meta = sf.info(wav)
            assert (meta.frames, meta.samplerate) == (info.frames, info.samplerate), (side, wav.name)
            shutil.copyfile(wav, case / side / wav.name)
        report = read_json(folder / "report.json")
        for stem, m in report["metrics"].items():
            summary["stems"].setdefault(stem, {})[side] = m.get("raw_sdr_db")
    write_json(case / "comparison.json", summary)
    print(case.name)
