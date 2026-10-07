"""Evaluate a proposed thirteenth family without altering existing analyses."""
from pathlib import Path
import numpy as np
import soundfile as sf
from music_analyzer.common import project_root,read_json,write_json
from music_analyzer.ground_truth import score
from music_analyzer.percussion_refinement import transfer

cases=project_root()/'data/ground-truth/cases';summary=[]
for case in sorted(cases.iterdir()):
    if not (case/'prepared.json').exists() or not (case/'run.json').exists():continue
    prepared=read_json(case/'prepared.json')
    if prepared.get('exclude_from_evaluation'):continue
    prediction=cases/'extended-head-study'/case.name/'percussion.wav'
    if not prediction.exists():continue
    run=read_json(case/'run.json');root=Path(run['root'])
    row=read_json(root/'web'/run['id']/'record.json')
    if row['state']!='SUCCEEDED':continue
    files={t['family']:root/t['path'] for t in row['tracks']}
    if (case/'without-recovery/other.wav').exists():files['other']=case/'without-recovery/other.wav'
    drum=sf.read(files['drums'],dtype='float32',always_2d=True)[0]
    other=sf.read(files['other'],dtype='float32',always_2d=True)[0]
    estimate=sf.read(prediction,dtype='float32',always_2d=True)[0]
    after_drums,after_other,percussion=transfer(drum,other,estimate,sf.read(prediction.with_name('timpani.wav'),dtype='float32',always_2d=True)[0])
    error=float(np.max(np.abs(drum.astype(float)+other-after_drums.astype(float)-after_other-percussion)))
    assert error<2e-6
    mix=sf.read(prepared['input'],dtype='float32',always_2d=True)[0]
    ref=prepared['references'].get('pitched_percussion')
    target=sf.read(ref['path'],dtype='float32',always_2d=True)[0] if ref else np.zeros_like(mix)
    ref=prepared['references'].get('drums')
    drum_target=sf.read(ref['path'],dtype='float32',always_2d=True)[0] if ref else np.zeros_like(mix)
    item={'case':case.name,'percussion':score(target,percussion,mix),
          'drums_before':score(drum_target,drum,mix),'drums_after':score(drum_target,after_drums,mix),
          'partition_max_abs_error':error}
    output=case/'percussion-candidate';output.mkdir(exist_ok=True)
    for family,audio in [('drums',after_drums),('other',after_other),('percussion',percussion)]:sf.write(output/(family+'.wav'),audio,44100,subtype='FLOAT')
    summary.append(item)
    print(case.name,item['percussion']['raw_sdr_db'],item['percussion']['output_to_mix_db'],
          item['drums_before']['raw_sdr_db'],item['drums_after']['raw_sdr_db'],flush=True)
write_json(project_root()/'docs/ADDITIONAL_PERCUSSION_RESULTS.json',summary)
