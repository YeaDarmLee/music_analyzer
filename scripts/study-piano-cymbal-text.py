"""Pinned CLAPSep cymbal candidates; inference only, never publishes user tracks."""
from music_analyzer import part_study
from music_analyzer.common import project_root,write_json,sha256_file
from pathlib import Path
import argparse
import soundfile as sf
parser=argparse.ArgumentParser()
parser.add_argument('--quiet-controls',action='store_true')
args=parser.parse_args()

root=project_root()
source=root/'data/ground-truth/cases/piano-drum-context-study'
output=root/'data/ground-truth/cases/piano-cymbal-text-study'
negative='piano playing melodic notes and chords'
part_study.PROMPTS['piano_cymbal']={'baseline':['drum kit and cymbals',negative],
    'a':['drum kit percussion and cymbals',negative],
    'b':['ride cymbal being struck with drumsticks',negative], 'labels':['drums','ride']}
cases=[]
if args.quiet_controls:
    piano=sf.read(source/'piano-only-control/piano-before.wav',dtype='float32',always_2d=True)[0]
    for name,gain in (('piano-only-quiet-control',.1),('piano-only-very-quiet-control',.01)):
        path=source/name/'piano-before.wav';path.parent.mkdir(exist_ok=True)
        sf.write(path,piano*gain,44100,subtype='FLOAT')
for folder in sorted(source.iterdir()):
    if not (folder/'piano-before.wav').exists():continue
    path=folder/'piano-before.wav'
    if args.quiet_controls and not folder.name.startswith('piano-only-') or args.quiet_controls and folder.name=='piano-only-control':continue
    cases.append({'name':folder.name,'family':'piano_cymbal','input':str(path),
                  'input_sha256':sha256_file(path),'output':str(output/folder.name),
                  'queries':['part_a','part_b']})
plan=output/'plan.json'
write_json(plan,{'data_root':str(root/'data/separation'),'cases':cases})
part_study.infer_plan(plan)
