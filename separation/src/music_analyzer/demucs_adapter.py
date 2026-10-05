from __future__ import annotations

import math
import random


def chunk_count(frames: int, rate: int, segment: float, overlap: float,
                shifts: int, models: int, seed: int) -> int:
    """Exactly mirror upstream random-shift lengths without consuming its RNG."""
    stride = int((1 - overlap) * int(rate * segment))
    if stride <= 0 or not 0 <= overlap < 1 or shifts < 0 or models < 1:
        raise ValueError("Invalid inference settings")
    rng = random.Random(seed)
    count = 0
    for _ in range(models):
        if not shifts:
            count += math.ceil(frames / stride)
        else:
            max_shift = int(.5 * rate)
            for _ in range(shifts):
                offset = rng.randint(0, max_shift)
                count += math.ceil((frames + max_shift - offset) / stride)
    return count


def model_members(model):
    from demucs.apply import BagOfModels
    return list(model.models) if isinstance(model, BagOfModels) else [model]


def configure_model(model, selected):
    from fractions import Fraction
    from .job_contracts import JobError
    members = model_members(model)
    trained = [float(member.segment) for member in members]
    override = selected["model_segment_override_sec"]
    if selected["segment_sec"] > min(trained) and override is None:
        raise JobError("MODEL_SEGMENT", "Input segment exceeds trained model length")
    if override is not None:
        if not 0 < override <= min(trained):
            raise JobError("MODEL_SEGMENT", "Invalid internal segment override")
        for member in members:
            member.segment = Fraction(str(override))
    model.eval()
    # Upstream BagOfModels moves one member to GPU at a time and returns it to CPU.
    if len(members) == 1:
        model.to("cuda")
    return trained, [float(member.segment) for member in members]
