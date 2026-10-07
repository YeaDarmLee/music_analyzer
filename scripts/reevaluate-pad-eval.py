"""Re-prepare cases whose reference policy changed and re-score existing pipeline outputs (no GPU)."""
from pathlib import Path
from music_analyzer.common import project_root,read_json,write_json
import numpy as np,soundfile as sf
from music_analyzer.audio import write_raw
from music_analyzer.common import sha256_file
from music_analyzer.ground_truth import prepare,evaluate
from music_analyzer.web_server import WebLibrary
base=project_root()/'data/pad-eval/cases';stems=project_root()/'data/pad-eval/stems'
for case in sorted(base.iterdir()):
    config=read_json(case/'case.json')
    if config['pad_timbre']%8 not in (6,7):continue
    if 'strings' in config['reference_sources']:
        config['reference_sources']['synth_strings']=config['reference_sources'].pop('strings')
        gains=config['reference_gains'];gains['synth_strings']=gains.pop('strings',.5)
    write_json(case/'case.json',config);prepare(case/'case.json')
    run=read_json(case/'run.json');root=Path(run['root']);row=read_json(root/'web'/run['id']/'record.json')
    # The reference sum changed only by float order; keep the exact audio the pipeline analyzed as the mix.
    library=WebLibrary.__new__(WebLibrary);library.root=root
    analyzed=sf.read(library.track_path(row,'original'),dtype='float32',always_2d=True)[0]
    prepared=read_json(case/'prepared.json');new=sf.read(prepared['input'],dtype='float32',always_2d=True)[0]
    assert float(np.abs(new-analyzed).max())<1e-6
    write_raw(Path(prepared['input']),analyzed);prepared['input_sha256']=sha256_file(Path(prepared['input']));write_json(case/'prepared.json',prepared)
    evaluate(case,root,row)
print('REEVALUATED')
