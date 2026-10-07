"""Exercise the actual publishing function on nine cached ground-truth analyses."""
import shutil
import uuid
from pathlib import Path
import numpy as np
import soundfile as sf
from music_analyzer.common import project_root,read_json,write_json,sha256_file
from music_analyzer.piano_drum_refinement import apply
from music_analyzer.ground_truth import score
from music_analyzer.web_server import WebLibrary

cases=project_root()/'data/ground-truth/cases'
summary=[]
for case in sorted(cases.iterdir()):
    if not (case/'run.json').exists():continue
    execution=read_json(case/'run.json');old_root=Path(execution['root'])
    old=read_json(old_root/'web'/execution['id']/'record.json')
    source=cases/'piano-cymbal-text-study'/case.name
    if not (source/'manifest.json').exists():continue
    root=case/'cymbal-v10-library';folder=root/'web'/('analysis_'+uuid.uuid4().hex)
    folder.mkdir(parents=True)
    tracks=[];before={}
    for track in old['tracks']:
        family=track['family']
        path=folder/(family+'.wav')
        original=cases/'piano-drum-context-study'/case.name/'piano-before.wav' if family=='piano' else case/'without-recovery'/(family+'.wav')
        shutil.copyfile(original,path)
        before[family]=sf.read(path,dtype='float32',always_2d=True)[0]
        tracks.append({**track,'path':str(path.relative_to(root)),'sha256':sha256_file(path)})
    row={k:v for k,v in old.items() if not k.endswith('_recovery')}
    shutil.copyfile(old_root/old['instrumental'],folder/'instrumental.wav')
    row.update(id=folder.name,tracks=tracks,separation_version='staged-guitar-residual-v10',
               instrumental=str((folder/'instrumental.wav').relative_to(root)))
    revised=apply(root,row,source/'part_b.wav',source/'manifest.json')
    arrays={t['family']:sf.read(root/t['path'],dtype='float32',always_2d=True)[0] for t in revised['tracks']}
    maximum=float(np.max(np.abs(sum(arrays.values())-sum(before.values()))))
    assert maximum<2e-6 and len(arrays)==12
    for family in set(arrays)-{'piano','drums'}:np.testing.assert_array_equal(before[family],arrays[family])
    library=WebLibrary(root)
    try:library.validate_partition(row['instrumental'],[t for t in revised['tracks'] if t['family'] not in ('lead','backing')])
    finally:library.executor.shutdown()
    prepared=read_json(case/'prepared.json');mix=sf.read(prepared['input'],dtype='float32',always_2d=True)[0]
    item={'case':case.name,'sum_max_abs_error':maximum,'method':'actual-apply-with-cached-inference','metrics':{}}
    for family in ('piano','drums'):
        reference=prepared['references'].get(family)
        target=sf.read(reference['path'],dtype='float32',always_2d=True)[0] if reference else np.zeros_like(mix)
        item['metrics'][family]={'before':score(target,before[family],mix),'after':score(target,arrays[family],mix)}
    summary.append(item)
    write_json(folder/'record.json',revised)
    print(case.name,'PUBLISH + PARTITION PASS',flush=True)
write_json(project_root()/'docs/PIANO_CYMBAL_SAMPLE_VERIFICATION.json',summary)
assert len(summary)==9
