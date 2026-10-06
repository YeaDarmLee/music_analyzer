"""Prepare paired presence, quiet and absence controls from two BabySlakh tracks."""
import argparse
import yaml

from music_analyzer.common import project_root,write_json,sha256_file
from music_analyzer.ground_truth import prepare

root = project_root()/'data/ground-truth'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--track',choices=['20','16'],default='20')
args = parser.parse_args()
if args.track == '16':
    start,label,target = 60,'brass','brass'
    selection = {'piano':[('S00',5),('S10',0)],'bass':[('S01',33)],
                 'guitar':[('S02',29),('S03',26),('S15',26)],'strings':[('S04',49),('S05',48)],
                 'brass':[('S06',61)],'drums':[('S09',128)],'other':[('S07',73),('S08',68),('S11',46)]}
    omitted = ['S12','S13','S14']
else:
    start,label,target = 15,'pad','synth'
    selection = {'drums':[('S00',128)],'bass':[('S01',33)],'synth':[('S02',88)],
                 'piano':[('S03',0)],'guitar':[('S04',27)],'strings':[('S05',48)]}
    omitted = ['S06','S07','S08','S09']
track = f'Track{int(args.track):05}'
source = root/'slakh'/track
metadata = yaml.safe_load((source/'metadata.yaml').read_text(encoding='utf-8'))
references = {}
for family,stems in selection.items():
    for stem,program in stems:
        if metadata['stems'][stem]['program_num'] != program:
            raise ValueError('Unexpected BabySlakh instrument mapping')
    references[family] = [f'../../slakh/{track}/stems/{stem}.wav' for stem,_ in stems]

for prefix,gain in [('',1),('quiet-',.1),('no-',0)]:
    case = root/'cases'/f'slakh{args.track}-{prefix}{label}-{start}-{start+15}'/'case.json'
    write_json(case, {'name':case.parent.name,'start_sec':start,'duration_sec':15,'has_bleed':False,
                     'reference_sources':references,'reference_gains':{target:gain},
                     'dataset_url':'https://zenodo.org/records/4603870','license':'CC BY 4.0',
                     'metadata_sha256':sha256_file(source/'metadata.yaml'),
                     'input_kind':'16kHz mono virtual-instrument stems; equal-gain remix converted to 44.1kHz stereo',
                     'scope':'controlled diagnostic; not a held-out real-recording quality benchmark',
                     'omitted_stems':omitted})
    prepare(case)
    print('PREPARED',case.parent.name,flush=True)
