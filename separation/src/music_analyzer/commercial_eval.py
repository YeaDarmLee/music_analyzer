"""Shared helpers for commercial-clean A/B evaluation (model loading, chunked inference, GT-free metrics)."""
from __future__ import annotations

import numpy as np
import soundfile as sf
import torch

from .common import project_root, read_json
from .evaluation import raw_sdr, si_sdr
from .roformer_runner import load_config, overlap_infer


def load_model(model_id: str):
    from .vendor.msst.bs_roformer import BSRoformer
    base = project_root()
    reg = read_json(base / f"data/separation/models/{model_id}/registration.json")
    cfg = load_config(reg)
    model = BSRoformer(**cfg["model"])
    weights = torch.load(base / "data/separation/models" / model_id / reg["checkpoint_filename"], map_location="cpu", weights_only=True)
    model.load_state_dict(weights.get("state_dict", weights), strict=True)
    model.eval().cuda()
    return model, reg, cfg["audio"]["chunk_size"]


def run(model, chunk: int, labels, audio: np.ndarray, overlap: float = .4, single: bool = False) -> dict[str, np.ndarray]:
    """audio: (samples, 2) float32 -> {label: (samples, 2)}. single=True: one-output model, second label = input - first (as the runner does)."""
    def infer(piece):
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
            out = model(torch.from_numpy(piece).unsqueeze(0).cuda())[0].float().cpu().numpy()
        return out[0] if single and out.ndim == 3 and out.shape[0] == 1 else out
    if single:
        first = overlap_infer(audio.T.copy(), chunk, overlap, infer).T
        return {labels[0]: first, labels[1]: audio - first}
    est = overlap_infer(audio.T.copy(), chunk, overlap, infer, output_stems=len(labels))
    return {label: e.T for label, e in zip(labels, est)}


def read_audio(path) -> np.ndarray:
    audio, rate = sf.read(path, dtype="float32", always_2d=True)
    if rate != 44100 or audio.shape[1] != 2:
        raise ValueError("expected 44.1 kHz stereo")
    return audio


def db(x) -> float:
    return float(20 * np.log10(np.sqrt(np.mean(np.asarray(x, np.float64) ** 2)) + 1e-12))


def partition_stats(original: np.ndarray, stems: list[np.ndarray]) -> dict:
    total = np.zeros(original.shape, np.float64)
    for s in stems:
        total += s
    err = total - original
    return {"max_abs_error": float(np.max(np.abs(err))), "rms_error": float(np.sqrt(np.mean(err ** 2))),
            "samples_over_2e-6": int(np.sum(np.abs(err) > 2e-6)), "nan": int(np.isnan(total).sum()), "inf": int(np.isinf(total).sum()),
            "clipping_samples": int(sum(np.sum(np.abs(s) > 1.0) for s in stems)),
            "dc_offset": float(max(abs(np.mean(s)) for s in stems))}


__all__ = ["load_model", "run", "read_audio", "db", "partition_stats", "raw_sdr", "si_sdr"]


def _explained(estimate: np.ndarray, reference: np.ndarray) -> float:
    r = reference.ravel().astype(np.float64); e = estimate.ravel().astype(np.float64)
    return float((np.dot(e, r) / (np.dot(r, r) + 1e-12)) ** 2 * np.dot(r, r))


def stem_metrics(target: np.ndarray, estimate: np.ndarray, others: list[np.ndarray]) -> dict:
    """sdr/si_sdr; est_vs_ref_db; leak_db = energy of the estimate explained by the other GT sources vs by the target (lower is better);
    missing_db = target energy the best scalar fit of the estimate does not reproduce, 10log10(|t-fit|^2/|t|^2) (lower is better)."""
    t = target.astype(np.float64); e = estimate.astype(np.float64)
    fit = (np.dot(t.ravel(), e.ravel()) / (np.dot(e.ravel(), e.ravel()) + 1e-12)) * e
    leak = sum(_explained(estimate, o) for o in others if np.any(o))
    return {"sdr": raw_sdr(target, estimate), "si_sdr": si_sdr(target, estimate), "est_vs_ref_db": db(estimate) - db(target),
            "leak_db": float(10 * np.log10((leak + 1e-12) / (_explained(estimate, target) + 1e-12))),
            "missing_db": float(10 * np.log10((np.sum((t - fit) ** 2) + 1e-12) / (np.sum(t ** 2) + 1e-12)))}
