import numpy as np
import soundfile as sf
import pytest
from music_analyzer.substem_experiment import prepare,publish,folder

def test_clip_and_residual_preserve_parent(tmp_path):
    source=tmp_path/"source.wav";audio=np.random.default_rng(4).normal(0,.1,(88200,2)).astype("float32");sf.write(source,audio,44100,subtype="FLOAT")
    row=prepare(tmp_path,source,"guitar",.5,1);out=folder(tmp_path,row["experiment_id"])
    clip,_=sf.read(out/"input.wav",dtype="float32",always_2d=True);np.testing.assert_array_equal(clip,audio[22050:66150])
    estimate=tmp_path/"estimate.wav";sf.write(estimate,clip*.3,44100,subtype="FLOAT")
    result=publish(tmp_path,row["experiment_id"],estimate,"test_fixture_only")
    target,_=sf.read(out/"target.wav",dtype="float32");residual,_=sf.read(out/"residual.wav",dtype="float32")
    np.testing.assert_allclose(target+residual,clip,atol=1e-7)
    assert result["state"]=="CANDIDATE_READY" and not result["quality_improvement_verified"]
    assert not result["model_inference_performed"]
    with pytest.raises(ValueError):publish(tmp_path,row["experiment_id"],estimate,"test")

def test_invalid_window_and_estimate_do_not_publish(tmp_path):
    source=tmp_path/"source.wav";sf.write(source,np.zeros((88200,2)),44100,subtype="FLOAT")
    for start,duration in [(float("nan"),1),(0,31),(1.5,1)]:
        with pytest.raises(ValueError):prepare(tmp_path,source,"vocals",start,duration)
    row=prepare(tmp_path,source,"vocals",0,1);estimate=tmp_path/"wrong.wav";sf.write(estimate,np.zeros((44100,1)),44100)
    with pytest.raises(ValueError):publish(tmp_path,row["experiment_id"],estimate,"test")
    with pytest.raises(ValueError):folder(tmp_path,"../../escape")
