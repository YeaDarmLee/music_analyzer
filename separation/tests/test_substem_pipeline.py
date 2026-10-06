import numpy as np
import pytest
import soundfile as sf
from music_analyzer.substem_pipeline import prepare_full
from music_analyzer.common import read_json,sha256_file
from music_analyzer.substem_experiment import folder


def test_full_parent_keeps_exact_stereo_timeline_and_hash(tmp_path):
    source=tmp_path/"source.wav";audio=np.random.default_rng(7).normal(0,.05,(44100*31+1,2)).astype(np.float32)
    sf.write(source,audio,44100,subtype="FLOAT")
    identifier,frames=prepare_full(tmp_path,source,"other")
    manifest=read_json(folder(tmp_path,identifier)/"manifest.json")
    restored,rate=sf.read(folder(tmp_path,identifier)/"input.wav",dtype="float32")
    assert frames==len(audio) and rate==44100
    np.testing.assert_array_equal(restored,audio)
    assert manifest["parent_sha256"]==sha256_file(source)
    assert manifest["timeline"]["start_frame"]==0
    assert not manifest["model_inference_performed"]


def test_full_parent_rejects_noncanonical_audio(tmp_path):
    source=tmp_path/"source.wav";sf.write(source,np.zeros(32000),32000)
    with pytest.raises(ValueError,match="Invalid full-length"):prepare_full(tmp_path,source,"guitar")
