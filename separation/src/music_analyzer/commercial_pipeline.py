"""commercial_13: final_11 architecture with every UNKNOWN-weight stage replaced by an APPROVED model.

final_11 stays the DEV baseline. Stage preset names used by Library.analyze are remapped here, and
registry.commercial_gate() refuses to start unless every model below is APPROVED with a pinned hash.
"""
from __future__ import annotations

from .common import read_json
from .job_contracts import preset
from .registry import APPROVAL

# final_11 stage preset -> commercial preset (stages not listed are reused unchanged)
STAGE_PRESETS = {
    "instrument_roformer_6s": "instrument_core4",   # was bs_6stem_fixed.ckpt (UNKNOWN)
    "bs_karaoke": "vocal2_mega",                    # was bs_roformer_karaoke_frazer_becruily.ckpt (UNKNOWN)
}
# stages shared with final_11 whose models are already approved
SHARED_PRESETS = ("vocal_roformer", "instrument_mega7", "instrument_mega5")


def stage_presets() -> list[str]:
    return [*SHARED_PRESETS, *STAGE_PRESETS.values()]


MODELS = tuple(dict.fromkeys(preset(name)["model_id"] for name in stage_presets()))


def blocked_models() -> dict[str, str]:
    approvals = read_json(APPROVAL)["models"]
    return {m: approvals.get(m, {}).get("status", "UNKNOWN") for m in MODELS if approvals.get(m, {}).get("status") != "APPROVED"}
