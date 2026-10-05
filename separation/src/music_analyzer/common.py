from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from uuid import uuid4


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, data: object) -> None:
    serialized = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".partial")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        # Windows readers/virus scanners may briefly hold the destination without delete sharing.
        for attempt in range(20):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(.025)
    finally:
        temporary.unlink(missing_ok=True)


def read_json(path: Path) -> dict:
    for attempt in range(20):
        try:
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(.025)


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]
