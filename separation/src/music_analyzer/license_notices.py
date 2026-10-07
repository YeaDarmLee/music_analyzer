"""Build and verify the public third-party notices (frontend/public/licenses/) from the production plan.

    production presets (release_presets.json, APPROVED) -> models they run -> cross-checked with commercial_approval.json
    runtime modules -> imported Python distributions -> must each have a notice here
    frontend package.json -> must each have a notice here

The build fails (and `check()` reports) when a production model has no notice or a blocking problem, when a notice is
shown for something production does not use, or when the committed files differ from what the plan produces.
Nothing public contains stage names, model roles or hashes.
"""
from __future__ import annotations

import importlib.metadata as metadata
import json
import re
import shutil
from pathlib import Path

from . import release
from .common import project_root, read_json

ROOT = project_root()
OUT = ROOT / "frontend/public/licenses"
NODE = ROOT / "frontend/node_modules"
SEP = "\n\n" + "-" * 72 + "\n\n"
MODEL_NOTICES = ROOT / "separation/configs/model_notices.json"

# normalized distribution name -> (slug, display name, license, official project, copyright holder override)
PYTHON = {
    "torch": ("pytorch", "PyTorch", "BSD-3-Clause", "https://pytorch.org/", None),
    "demucs": ("demucs", "Demucs", "MIT", "https://github.com/facebookresearch/demucs", None),
    "rotary-embedding-torch": ("rotary-embedding-torch", "rotary-embedding-torch", "MIT", "https://github.com/lucidrains/rotary-embedding-torch", None),
    "einops": ("einops", "einops", "MIT", "https://github.com/arogozhnikov/einops", None),
    "beartype": ("beartype", "beartype", "MIT", "https://github.com/beartype/beartype", None),
    "pyyaml": ("pyyaml", "PyYAML", "MIT", "https://pyyaml.org/", None),
    "numpy": ("numpy", "NumPy", "BSD-3-Clause", "https://numpy.org/", None),
    "scipy": ("scipy", "SciPy", "BSD-3-Clause", "https://scipy.org/", None),
    "soundfile": ("python-soundfile", "python-soundfile", "BSD-3-Clause", "https://github.com/bastibe/python-soundfile", None),
    "filelock": ("filelock", "filelock", "MIT", "https://github.com/tox-dev/filelock", None),
    "psutil": ("psutil", "psutil", "BSD-3-Clause", "https://github.com/giampaolo/psutil", None),
    "pymysql": ("pymysql", "PyMySQL", "MIT", "https://github.com/PyMySQL/PyMySQL", None),
    "cryptography": ("cryptography", "cryptography", "Apache-2.0 OR BSD-3-Clause", "https://github.com/pyca/cryptography",
                     "The Python Cryptographic Authority and individual contributors"),
    "librosa": ("librosa", "librosa", "ISC", "https://librosa.org/", None),
    "packaging": ("packaging", "packaging", "Apache-2.0 OR BSD-2-Clause", "https://github.com/pypa/packaging", None),
}
# not pip distributions: name -> notice key used by config["external_tools"] / the vendored module path
FFMPEG = {"name": "FFmpeg (외부 프로세스로 실행)", "version": "빌드에 따라 다름", "copyright": "the FFmpeg developers",
          "license": "LGPL-2.1+ 또는 GPL-2.0+ (빌드 구성에 따라 다름)", "url": "https://ffmpeg.org/", "text": "https://ffmpeg.org/legal.html"}
FONT_VERSION = "5.3.0"  # @fontsource-variable/manrope and @fontsource-variable/noto-sans-kr, vendored in frontend/public/fonts
# package.json name -> (slug, display name, license, official project, license file, copyright override)
WEB = {
    "vue": ("vue", "Vue", "MIT", "https://vuejs.org/", NODE / "vue/LICENSE", None),
    "@lucide/vue": ("lucide-vue", "@lucide/vue", "ISC · MIT(일부 아이콘)", "https://lucide.dev/", NODE / "@lucide/vue/LICENSE", None),
    "@mdi/js": ("mdi-js", "@mdi/js (Material Design Icons)", "Apache-2.0", "https://pictogrammers.com/library/mdi/", NODE / "@mdi/js/LICENSE", "AUTHOR"),
}
FONTS = [
    ("manrope", "Manrope (웹 폰트)", "OFL-1.1", "https://github.com/sharanda/manrope", ROOT / "frontend/public/fonts/LICENSE-manrope.txt",
     "Copyright 2019 The Manrope Project Authors"),
    ("noto-sans-kr", "Noto Sans KR (웹 폰트)", "OFL-1.1", "https://fonts.google.com/noto/specimen/Noto+Sans+KR",
     ROOT / "frontend/public/fonts/LICENSE-noto-sans-kr.txt", "Google Inc."),
]


def _license_files(dist_name):
    dist = metadata.distribution(dist_name)
    base = Path(dist.locate_file(""))
    found = [base / f for f in dist.files or []
             if re.match(r"(LICEN[CS]E|COPYING)", f.name, re.I) and (f.parent.name.endswith(".dist-info") or f.parent.name == "licenses")]
    if not found:
        raise release.ReleaseError(f"NOTICE_LICENSE_FILE_MISSING: {dist_name}")
    return sorted(found, key=lambda p: (p.name != "LICENSE" and p.name != "LICENSE.md" and p.name != "LICENSE.txt", p.name))


def _holder(text):
    match = re.search(r"^\s*(Copyright[^\n]*)$", text, re.MULTILINE | re.IGNORECASE)
    return match.group(1).strip() if match else "라이선스 전문 참조"


def _entry(texts, rows, slug, name, version, license_id, url, sources, holder=None):
    text = SEP.join(Path(p).read_text(encoding="utf-8", errors="replace") for p in sources)
    texts[slug] = text
    rows.append({"name": name, "version": version, "copyright": holder or _holder(text), "license": license_id,
                 "url": url, "text": f"/licenses/texts/{slug}.txt"})


def model_entries(plan_models, group_config):
    """Collapse production models into notice entries. Returns (entries, problems)."""
    entries, problems, groups = [], [], {}
    for record in plan_models:
        group = group_config["models"].get(record["model_id"])
        if group is None or group not in group_config["groups"]:
            problems.append(f"missing license notice: production model {record['model_id']} has no entry in model_notices.json")
            continue
        groups.setdefault(group, []).append(record)
    for group, records in sorted(groups.items()):
        licenses = {r["weight_license"] for r in records}
        evidence = sorted({r["approval_evidence_url"] for r in records if r.get("approval_evidence_url")})
        if len(licenses) != 1 or not evidence:
            problems.append(f"notice group {group}: inconsistent weight license or missing evidence")
            continue
        info = group_config["groups"][group]
        entries.append({"name": info["name"], "author": info["author"], "license": f"{licenses.pop()} (저작자 선언)",
                        "url": info["url"], "evidence": evidence[0]})
    return entries, problems


def compute(plan=None, group_config=None):
    """The exact notice set production implies, plus every blocking problem found while computing it."""
    plan = release.manifest() if plan is None else plan
    group_config = read_json(MODEL_NOTICES) if group_config is None else group_config
    problems = [f"{name}: {p}" for name in plan["production_presets"] for p in plan["presets"][name]["problems"]]
    texts, server, web = {}, [], []
    runtime = plan["runtime"]
    for dist in sorted(runtime["direct"]):
        if dist not in PYTHON:
            problems.append(f"missing license notice: runtime package {dist} has no entry in license_notices.PYTHON")
            continue
        slug, name, license_id, url, holder = PYTHON[dist]
        _entry(texts, server, slug, name, runtime["direct"][dist].split("+")[0], license_id, url, _license_files(dist), holder)
    for dist in sorted(set(PYTHON) - set(runtime["direct"])):
        problems.append(f"notice for {dist} would describe a package production does not import")
    modules = read_json(release.CONFIG)["commercial"]["runtime_modules"]
    if any(m.startswith("vendor/msst/") for m in modules):
        msst = ROOT / "separation/src/music_analyzer/vendor/msst"
        revision = json.loads((msst / "PROVENANCE.json").read_text(encoding="utf-8"))["revision"][:7]
        _entry(texts, server, "msst", "Music-Source-Separation-Training (일부 수정하여 포함)", "rev " + revision, "MIT",
               "https://github.com/ZFTurbo/Music-Source-Separation-Training", [msst / "LICENSE"])
    tools = set(runtime["external_tools"])
    if "libsndfile" in tools:
        import soundfile
        _entry(texts, server, "libsndfile", "libsndfile (python-soundfile에 포함)", soundfile.__libsndfile_version__, "LGPL-2.1",
               "https://libsndfile.github.io/libsndfile/", [Path(soundfile.__file__).parent / "_soundfile_data/COPYING"],
               "libsndfile contributors (python-soundfile 동봉 COPYING 참조)")
    if "FFmpeg" in tools:
        server.append(dict(FFMPEG))
    unknown = tools - {"libsndfile", "FFmpeg"}
    if unknown:
        problems.append(f"missing license notice: external tools {sorted(unknown)}")
    package = json.loads((ROOT / "frontend/package.json").read_text(encoding="utf-8"))
    for dep in package.get("dependencies", {}):
        if dep not in WEB:
            problems.append(f"missing license notice: frontend dependency {dep}")
    for dep, (slug, name, license_id, url, source, holder) in WEB.items():
        if dep not in package.get("dependencies", {}):
            problems.append(f"notice for {dep} would describe a frontend package that is not a dependency")
        elif not source.exists():
            problems.append(f"frontend dependencies are not installed ({dep}); run npm ci")
        else:
            meta = json.loads((source.parent / "package.json").read_text(encoding="utf-8"))
            _entry(texts, web, slug, name, meta["version"], license_id, url, [source], meta["author"] if holder == "AUTHOR" else None)
    for slug, name, license_id, url, source, holder in FONTS:
        _entry(texts, web, slug, name, FONT_VERSION, license_id, url, [source], holder)
    production_models = {}
    for name in plan["production_presets"]:
        for record in plan["presets"][name]["models"]:
            production_models[record["model_id"]] = record
    models, model_problems = model_entries(list(production_models.values()), group_config)
    return {"components": {"server": server, "web": web}, "models": models, "texts": texts}, problems + model_problems


def build(out=OUT):
    plan = release.validate_production()
    notices, problems = compute(plan)
    if problems:
        raise release.ReleaseError("NOTICE_BUILD_FAILED: " + "; ".join(problems))
    shutil.rmtree(out, ignore_errors=True)
    (out / "texts").mkdir(parents=True)
    for slug, text in notices["texts"].items():
        (out / "texts" / f"{slug}.txt").write_text(text, encoding="utf-8")
    (out / "components.json").write_text(json.dumps(notices["components"], ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "models.json").write_text(json.dumps(notices["models"], ensure_ascii=False, indent=1), encoding="utf-8")
    return notices


def check(out=OUT, plan=None, group_config=None):
    """Problems if the committed notice files differ from what production implies (empty list = in sync)."""
    notices, problems = compute(plan, group_config)
    try:
        shown_models = json.loads((out / "models.json").read_text(encoding="utf-8"))
        shown = json.loads((out / "components.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return problems + [f"notice files unreadable: {error}"]
    for entry in notices["models"]:
        if entry not in shown_models:
            problems.append(f"production model missing from /licenses: {entry['name']}")
    for entry in shown_models:
        if entry not in notices["models"]:
            problems.append(f"/licenses shows a model production does not use: {entry['name']}")
    for section in ("server", "web"):
        if shown.get(section) != notices["components"][section]:
            problems.append(f"/licenses {section} components differ from the production runtime")
    for slug, text in notices["texts"].items():
        path = out / "texts" / f"{slug}.txt"
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            problems.append(f"license text missing or stale: {slug}")
    return problems
