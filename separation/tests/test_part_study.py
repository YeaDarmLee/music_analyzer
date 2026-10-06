import numpy as np
import pytest
import soundfile as sf

from music_analyzer.part_study import diagnostics, reference_metrics, synth_controls


def test_duplicate_tracks_are_not_reported_as_accuracy():
    t = np.arange(1000)
    a = np.column_stack([np.sin(t * .2), np.cos(t * .3)])
    result = diagnostics(a, a * .6, a * .4)
    assert result["waveform_correlation"] == pytest.approx(1)
    assert result["sum_error_rms"] < 1e-15
    assert result["accuracy_score"] is None  # Perfect reconstruction can still be a duplicated line.


def test_true_sources_outperform_unseparated_mixture_and_wrong_source():
    t = np.arange(10000)
    a, b = np.sin(t*.2), np.cos(t*.137)
    perfect = reference_metrics(a, a, b)
    mixture = reference_metrics(a+b, a, b)
    wrong = reference_metrics(b, a, b)
    assert perfect["si_sdr_db"] > mixture["si_sdr_db"] > wrong["si_sdr_db"]
    assert mixture["interference_coefficient"] == pytest.approx(1)
    assert perfect["interference_coefficient"] == pytest.approx(0, abs=1e-10)


def test_control_preserves_wet_parts_and_does_not_invent_second_ground_truth(tmp_path):
    cases = synth_controls(tmp_path, duration=5)
    mixture, rate = sf.read(cases[0]["input"], dtype="float32", always_2d=True)
    pad, _ = sf.read(cases[0]["truth"][0], dtype="float32", always_2d=True)
    arp, _ = sf.read(cases[0]["truth"][1], dtype="float32", always_2d=True)
    single, _ = sf.read(cases[1]["input"], dtype="float32", always_2d=True)
    assert rate == 44100 and mixture.shape == (5*44100, 2)
    np.testing.assert_allclose(mixture, pad+arp, atol=1e-7)
    np.testing.assert_array_equal(single, pad)
    assert cases[1]["single_part_control"] and "truth" not in cases[1]


def test_invalid_timelines_are_not_scored():
    with pytest.raises(ValueError): diagnostics(np.zeros((10, 2)), np.zeros((11, 2)), np.zeros((10, 2)))
    assert reference_metrics(np.zeros(10), np.zeros(10), np.ones(10))["si_sdr_db"] is None
