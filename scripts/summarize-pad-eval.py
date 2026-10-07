"""Summarize pad-eval reports: pad recovery, strings damage, no-pad false synth, by split and kind."""
import json,sys
import numpy as np
from pathlib import Path
from music_analyzer.common import project_root,read_json,write_json

base=project_root()/'data/pad-eval/cases';tag=sys.argv[1] if len(sys.argv)>1 else 'v15'
rows=[]
for case in sorted(base.iterdir()):
    if not (case/'report.json').exists():continue
    c=read_json(case/'case.json');m=read_json(case/'report.json')['metrics']
    rows.append({'case':case.name,'split':c['split'],'kind':c['kind'],'timbre':c['pad_timbre'],
        'synth_sdr':m['synth']['raw_sdr_db'],'synth_capture':m['synth']['target_gain'],'synth_to_mix':m['synth']['output_to_mix_db'],
        'strings_sdr':m['strings']['raw_sdr_db'],'strings_capture':m['strings']['target_gain'],
        'strings_pad_leak':None})
def stat(v):
    v=[x for x in v if x is not None]
    return None if not v else {'n':len(v),'median':round(float(np.median(v)),3),'min':round(float(min(v)),3),'max':round(float(max(v)),3)}
out={'tag':tag,'cases_done':len(rows),'groups':{}}
for kind in ('pad_with_strings','quiet_pad','pad_piano_only','no_pad_control'):
    for split in ('dev','test','all'):
        sel=[r for r in rows if r['kind']==kind and (split=='all' or r['split']==split)]
        if not sel:continue
        out['groups'][f'{kind}/{split}']={'synth_sdr':stat([r['synth_sdr'] for r in sel]),'synth_capture':stat([r['synth_capture'] for r in sel]),
            'strings_sdr':stat([r['strings_sdr'] for r in sel]),'strings_capture':stat([r['strings_capture'] for r in sel]),
            'synth_to_mix_db':stat([r['synth_to_mix'] for r in sel])}
write_json(project_root()/f'docs/PAD_EVAL_{tag.upper()}.json',{**out,'cases':rows})
for k,v in out['groups'].items():print(k,json.dumps(v,ensure_ascii=False))
