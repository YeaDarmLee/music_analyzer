import numpy as np
import pytest
import soundfile as sf

from music_analyzer.commercial_cymbal import VERSION, apply as cymbal_apply
from music_analyzer.commercial_eval import partition_stats
from music_analyzer.vocal_split import split


def noise(seed, n=44100 * 3, scale=.1):
    return (np.random.default_rng(seed).standard_normal((n, 2)) * scale).astype(np.float32)


def test_vocal_split_preserves_sum_and_ignores_head_gain():
    vocals, lead, backing = noise(1), noise(2), noise(3, scale=.03)
    a, b = split(vocals, lead, backing)
    assert np.max(np.abs(a.astype(np.float64) + b - vocals)) < 2e-7
    a2, b2 = split(vocals, lead * 2, backing * 2)  # heads run ~2x loud on isolated vocals; only the ratio matters
    assert np.allclose(b, b2, atol=1e-5)


def test_vocal_split_rejects_mismatch_and_nan():
    with pytest.raises(ValueError):
        split(noise(1), noise(2, n=5000), noise(3))
    bad = noise(2)
    bad[10, 0] = np.nan
    with pytest.raises(ValueError):
        split(noise(1), bad, noise(3))


def test_vocal_split_silent_backing_keeps_vocals_as_lead():
    vocals = noise(1)
    lead, backing = split(vocals, vocals.copy(), np.zeros_like(vocals))
    assert np.max(np.abs(backing)) == 0 and np.allclose(lead, vocals)


def test_cymbal_transfer_preserves_pair_sum_and_records_backup(tmp_path):
    n = 44100 * 4
    t = np.arange(n) / 44100
    piano = np.stack([np.sin(2 * np.pi * 440 * t)] * 2, axis=1).astype(np.float32) * .2
    hiss = noise(5, n, .05)
    piano_with_leak = piano + hiss * (np.arange(n) % 22050 < 3000)[:, None]
    drums = hiss.copy()
    folder = tmp_path / "web" / "a1"
    folder.mkdir(parents=True)
    for name, audio in (("piano", piano_with_leak), ("drums", drums)):
        sf.write(folder / f"{name}.wav", audio, 44100, subtype="FLOAT")
    row = {"id": "a1", "tracks": [{"family": "piano", "path": "web/a1/piano.wav"}, {"family": "drums", "path": "web/a1/drums.wav"}]}
    out = cymbal_apply(tmp_path, row)
    assert out["cymbal_recovery"]["version"] == VERSION and out["cymbal_recovery"]["pair_max_abs_error"] < 2e-7
    assert (folder / "record-before-cymbal-commercial-v1.json").exists()
    new = {t["family"]: sf.read(tmp_path / t["path"], dtype="float32", always_2d=True)[0] for t in out["tracks"]}
    assert np.max(np.abs(new["piano"].astype(np.float64) + new["drums"] - piano_with_leak - drums)) < 2e-7
    assert cymbal_apply(tmp_path, out) is out  # idempotent


def test_partition_stats_flags_errors_and_nonfinite():
    original = noise(1)
    good = partition_stats(original, [original * .4, original * .6])
    assert good["max_abs_error"] < 1e-7 and good["nan"] == 0 and good["samples_over_2e-6"] == 0
    bad = partition_stats(original, [original * .5, original * .6])
    assert bad["samples_over_2e-6"] > 0
    nan = original.copy()
    nan[0, 0] = np.nan
    assert partition_stats(original, [nan])["nan"] == 1
