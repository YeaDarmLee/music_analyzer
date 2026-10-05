import numpy as np
import pytest
import yaml
from music_analyzer.roformer_runner import overlap_infer, ConfigLoader, load_config
from music_analyzer.registry import config

@pytest.mark.parametrize("frames",[1,127,1000,4097])
@pytest.mark.parametrize("overlap",[0,.5,.75])
def test_overlap_preserves_stereo_timeline_and_amplitude(frames,overlap):
    audio=np.random.default_rng(42).normal(size=(2,frames)).astype(np.float32)*2
    result=overlap_infer(audio,512,overlap,lambda x:x)
    assert result.shape==audio.shape
    np.testing.assert_allclose(result,audio,rtol=2e-6,atol=2e-6)

def test_nonfinite_model_output_rejected():
    with pytest.raises(ValueError,match="Invalid RoFormer"):
        overlap_infer(np.ones((2,100),dtype=np.float32),64,.5,lambda x:x*np.nan)

def test_safe_yaml_allows_tuple_but_rejects_objects():
    assert yaml.load("x: !!python/tuple [1,2]",Loader=ConfigLoader)["x"]==(1,2)
    with pytest.raises(yaml.constructor.ConstructorError):
        yaml.load("!!python/object/apply:os.system ['echo unsafe']",Loader=ConfigLoader)

def test_pinned_vendor_and_configuration_validate():
    configuration=load_config(config("melband_roformer_kj"))
    assert configuration["model"]["sample_rate"]==44100
    assert configuration["model"]["num_stems"]==1

def test_cancellation_stops_chunk_processing():
    def cancel(): raise RuntimeError("cancelled")
    with pytest.raises(RuntimeError,match="cancelled"):
        overlap_infer(np.ones((2,100),dtype=np.float32),64,.5,lambda x:x,cancel)

@pytest.mark.parametrize("overlap",[0,.5,.75])
def test_multistem_overlap_preserves_order_and_independent_outputs(overlap):
    audio=np.random.default_rng(8).normal(size=(2,4097)).astype(np.float32)
    factors=np.array([1,2,-3,4,0,.01],dtype=np.float32)
    result=overlap_infer(audio,512,overlap,lambda x:factors[:,None,None]*x,output_stems=6)
    assert result.shape==(6,2,4097)
    np.testing.assert_allclose(result,factors[:,None,None]*audio,rtol=2e-6,atol=2e-6)

def test_multistem_missing_head_rejected():
    with pytest.raises(ValueError,match="Invalid RoFormer"):
        overlap_infer(np.ones((2,100),dtype=np.float32),64,.5,
                      lambda x:np.stack([x]*5),output_stems=6)

def test_multistem_source_contract_and_vendor():
    entry=config("bs_roformer_6s")
    configuration=load_config(entry)
    assert configuration["model"]["num_stems"]==6
    assert configuration["training"]["instruments"]==entry["source_labels"]
