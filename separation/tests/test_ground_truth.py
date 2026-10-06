import numpy as np
import pytest
from music_analyzer.ground_truth import score


def test_reference_metrics_detect_gain_loss_and_false_output():
    t = np.arange(44100)/44100
    target = np.column_stack([.1*np.sin(2*np.pi*440*t)]*2)
    interference = np.column_stack([.1*np.sin(2*np.pi*770*t)]*2)
    mix = target+interference
    correct = score(target,target,mix)
    reduced = score(target,target*.1,mix)
    leaked = score(target,target+interference,mix)
    absent = score(np.zeros_like(target),interference,mix)
    assert correct['raw_sdr_db'] > leaked['raw_sdr_db']
    assert reduced['target_gain'] == pytest.approx(.1)
    assert absent['reference_absent'] and absent['raw_sdr_db'] is None
    assert absent['output_to_mix_db'] == pytest.approx(-3.0103,abs=1e-4)
    quiet = score(target*.001,target*.0001,mix)
    assert quiet['target_gain'] == pytest.approx(.1)
    assert quiet['error_rms'] > 0
    silence = np.zeros_like(target)
    assert score(silence,silence,silence)['output_to_mix_db'] is None
    with pytest.raises(ValueError):
        score(target,target[:-1],mix)
