import numpy as np
import pytest
import yaml
from music_analyzer.roformer_runner import overlap_infer, ConfigLoader, load_config
from music_analyzer.registry import config

@pytest.mark.parametrize("frames",[1,127,1000,4097])
@pytest.mark.parametrize("overlap",[0,.5,.75])
def test_skip_tail_windows_matches_previous_chunk_dependent_inference(frames,overlap):
    chunk=64;stride=max(1,int(chunk*(1-overlap)));border=chunk-stride
    audio=np.random.default_rng(7).normal(size=(2,frames)).astype(np.float32)
    padded=np.pad(audio,((0,0),(border,border)),mode="reflect" if frames>1 else "edge")
    result=np.zeros_like(padded);weights=np.zeros(padded.shape[1],dtype=np.float32)
    fade=max(1,chunk//10);window=np.ones(chunk,dtype=np.float32)
    window[:fade]=np.linspace(1/fade,1,fade,dtype=np.float32);window[-fade:]=window[:fade][::-1]
    def infer(piece):return piece*.7+piece.mean(axis=1,keepdims=True)*.3
    for offset in range(0,padded.shape[1],stride):
        length=min(chunk,padded.shape[1]-offset)
        piece=np.pad(padded[:,offset:offset+length],((0,0),(0,chunk-length)))
        result[:,offset:offset+length]+=infer(piece)[:,:length]*window[:length]
        weights[offset:offset+length]+=window[:length]
    expected=(result/weights)[:,border:border+frames]
    calls=[]
    actual=overlap_infer(audio,chunk,overlap,lambda x:(calls.append(1),infer(x))[1])
    np.testing.assert_array_equal(actual,expected)
    assert len(calls)==len(range(0,border+frames,stride))

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

def test_final_instrument_source_contract_and_vendor():
    entry=config("bs_roformer_mega4")
    configuration=load_config(entry)
    assert configuration["model"]["num_stems"]==4
    assert configuration["training"]["instruments"]==["acoustic-guitar","electric-guitar","synth","bowed_strings"]


def test_bs_karaoke_pinned_config_is_single_target_with_residual():
    registration=config("bs_karaoke")
    configuration=load_config(registration)
    assert registration["source_labels"]==["lead","backing"]
    assert registration["multi_output"] is False
    assert configuration["model"]["num_stems"]==1
    assert configuration["training"]["target_instrument"]=="Vocals"
