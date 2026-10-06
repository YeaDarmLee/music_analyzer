import numpy as np
import pytest
from music_analyzer.audiosep_experiment import restore_channel

@pytest.mark.parametrize("frames",[1,44100,44101,882000])
def test_polyphase_restoration_matches_original_frame_count(frames):
    native=np.zeros((frames*32000+44099)//44100,dtype=np.float32)
    restored=restore_channel(native,frames)
    assert restored.shape==(frames,)
    assert np.isfinite(restored).all()

@pytest.mark.parametrize("prediction",[np.zeros(3),np.full(32000,np.nan),np.zeros((32000,1))])
def test_invalid_model_timeline_is_rejected(prediction):
    with pytest.raises(ValueError):restore_channel(prediction,44100)
