import pytest
from music_analyzer import pipeline
from music_analyzer.job_contracts import JobError

@pytest.mark.parametrize("state,model,code",[
    ("FAILED","melband_roformer_kj","VOCAL_STAGE_FAILED"),
    ("SUCCEEDED","demucs_htdemucs","VOCAL_MODEL")])
def test_invalid_vocal_stage_stops_before_instruments(tmp_path,monkeypatch,state,model,code):
    class Service:
        def __init__(self,root): pass
        def status(self,job): return {"state":state,"model_id":model}
        def run(self,*args): pytest.fail("Instrument stage must not run")
    monkeypatch.setattr(pipeline,"JobService",Service)
    with pytest.raises(JobError) as error:
        pipeline.run_pipeline(tmp_path,vocal_job_id="old")
    assert error.value.code==code
