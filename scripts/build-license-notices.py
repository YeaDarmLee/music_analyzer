"""Regenerate frontend/public/licenses/ (third-party notices) from installed packages and the model approval file.

Only components that the running service actually uses are listed, and model weights appear only when
separation/configs/commercial_approval.json marks them APPROVED. Nothing here describes how components are combined.
Run after changing dependencies or model approvals:  .venv\\Scripts\\python.exe scripts\\build-license-notices.py
"""
from __future__ import annotations

import importlib.metadata as metadata
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "frontend/public/licenses"
SITE = Path(metadata.distribution("numpy").locate_file(""))
NODE = ROOT / "frontend/node_modules"
SEPARATOR = "\n\n" + "-" * 72 + "\n\n"

# (slug, display name, license id, official project, license file, version source)
PYTHON = [
    ("pytorch", "PyTorch", "BSD-3-Clause", "https://pytorch.org/", "torch", "torch"),
    ("demucs", "Demucs", "MIT", "https://github.com/facebookresearch/demucs", "demucs", "demucs"),
    ("rotary-embedding-torch", "rotary-embedding-torch", "MIT", "https://github.com/lucidrains/rotary-embedding-torch", "rotary_embedding_torch", "rotary-embedding-torch"),
    ("einops", "einops", "MIT", "https://github.com/arogozhnikov/einops", "einops", "einops"),
    ("beartype", "beartype", "MIT", "https://github.com/beartype/beartype", "beartype", "beartype"),
    ("pyyaml", "PyYAML", "MIT", "https://pyyaml.org/", "pyyaml", "PyYAML"),
    ("numpy", "NumPy", "BSD-3-Clause", "https://numpy.org/", "numpy", "numpy"),
    ("scipy", "SciPy", "BSD-3-Clause", "https://scipy.org/", "scipy", "scipy"),
    ("python-soundfile", "python-soundfile", "BSD-3-Clause", "https://github.com/bastibe/python-soundfile", "soundfile", "soundfile"),
    ("filelock", "filelock", "MIT", "https://github.com/tox-dev/filelock", "filelock", "filelock"),
    ("psutil", "psutil", "BSD-3-Clause", "https://github.com/giampaolo/psutil", "psutil", "psutil"),
    ("pymysql", "PyMySQL", "MIT", "https://github.com/PyMySQL/PyMySQL", "pymysql", "PyMySQL"),
    ("cryptography", "cryptography", "Apache-2.0 OR BSD-3-Clause", "https://github.com/pyca/cryptography", "cryptography", "cryptography"),
]
FRONTEND = [
    ("vue", "Vue", "MIT", "https://vuejs.org/", NODE / "vue/LICENSE", NODE / "vue/package.json"),
    ("lucide-vue", "@lucide/vue", "ISC · MIT(일부 아이콘)", "https://lucide.dev/", NODE / "@lucide/vue/LICENSE", NODE / "@lucide/vue/package.json"),
    ("mdi-js", "@mdi/js (Material Design Icons)", "Apache-2.0", "https://pictogrammers.com/library/mdi/", NODE / "@mdi/js/LICENSE", NODE / "@mdi/js/package.json"),
]


def dist_license(dist_name: str) -> Path:
    dist = metadata.distribution(dist_name)
    base = Path(dist.locate_file(""))
    for entry in dist.files or []:
        name = entry.name.upper()
        if entry.parent.name.endswith(".dist-info") or entry.parent.name == "licenses":
            if name in ("LICENSE", "LICENSE.TXT") :
                return base / entry
    raise SystemExit(f"license file not found for {dist_name}")


def copyright_line(text: str) -> str:
    match = re.search(r"^\s*(Copyright[^\n]*)$", text, re.MULTILINE | re.IGNORECASE)
    return match.group(1).strip() if match else "라이선스 전문 참조"


def add(rows, slug, name, version, license_id, url, source, copyright_text=None):
    target = OUT / "texts" / (slug + ".txt")
    text = SEPARATOR.join(path.read_text(encoding="utf-8", errors="replace") for path in ([source] if isinstance(source, Path) else source))
    target.write_text(text, encoding="utf-8")
    rows.append({"name": name, "version": version, "copyright": copyright_text or copyright_line(text),
                 "license": license_id, "url": url, "text": f"/licenses/texts/{slug}.txt"})


def main():
    shutil.rmtree(OUT, ignore_errors=True)
    (OUT / "texts").mkdir(parents=True)
    server, web = [], []
    for slug, name, license_id, url, dist_name, package in PYTHON:
        source, holder = dist_license(dist_name), None
        if slug == "cryptography":  # dual-licensed: the top-level file only points at the two texts
            source = [source, source.with_name("LICENSE.APACHE"), source.with_name("LICENSE.BSD")]
            holder = "The Python Cryptographic Authority and individual contributors"
        add(server, slug, name, metadata.version(package).split("+")[0], license_id, url, source, holder)
    msst = ROOT / "separation/src/music_analyzer/vendor/msst"
    revision = json.loads((msst / "PROVENANCE.json").read_text(encoding="utf-8"))["revision"][:7]
    add(server, "msst", "Music-Source-Separation-Training (일부 수정하여 포함)", "rev " + revision, "MIT",
        "https://github.com/ZFTurbo/Music-Source-Separation-Training", msst / "LICENSE")
    import soundfile
    add(server, "libsndfile", "libsndfile (python-soundfile에 포함)", soundfile.__libsndfile_version__, "LGPL-2.1",
        "https://libsndfile.github.io/libsndfile/", Path(soundfile.__file__).parent / "_soundfile_data/COPYING",
        "libsndfile contributors (python-soundfile 동봉 COPYING 참조)")
    server.append({"name": "FFmpeg (외부 프로세스로 실행)", "version": "빌드에 따라 다름", "copyright": "the FFmpeg developers",
                   "license": "LGPL-2.1+ 또는 GPL-2.0+ (빌드 구성에 따라 다름)", "url": "https://ffmpeg.org/",
                   "text": "https://ffmpeg.org/legal.html"})
    for slug, name, license_id, url, license_path, package_json in FRONTEND:
        package = json.loads(package_json.read_text(encoding="utf-8"))
        add(web, slug, name, package["version"], license_id, url, license_path,
            package["author"] if slug == "mdi-js" else None)

    approvals = json.loads((ROOT / "separation/configs/commercial_approval.json").read_text(encoding="utf-8"))["models"]
    groups = {}
    for model_id, entry in approvals.items():
        if entry["status"] == "APPROVED":
            groups.setdefault(entry["evidence_url"], []).append(model_id)
    names = {"huggingface.co/KimberleyJSN": ("Mel-Band RoFormer 가중치", "Kimberley Jensen (KimberleyJSN)", "https://huggingface.co/KimberleyJSN/melbandroformer"),
             "github.com/ZFTurbo": ("MVSep Mega53 계열 가중치", "MVSep / Roman Solovyev (ZFTurbo)", "https://github.com/ZFTurbo/Music-Source-Separation-Training")}
    models = []
    for evidence, ids in groups.items():
        name, author, project = next(v for k, v in names.items() if k in evidence)
        models.append({"name": name, "author": author, "license": "MIT (저작자 선언)", "url": project, "evidence": evidence})
    (OUT / "components.json").write_text(json.dumps({"server": server, "web": web}, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "models.json").write_text(json.dumps(models, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(server)} server, {len(web)} web, {len(models)} model entries")


if __name__ == "__main__":
    main()
