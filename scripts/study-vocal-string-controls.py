"""Real vocals overlapping real violin: validate restoration without erasing quiet singing."""
import time
from pathlib import Path
import numpy as np
import soundfile as sf
from music_analyzer.common import project_root,read_json,write_json
from music_analyzer.ground_truth import prepare,score
from music_analyzer.ingest import ingest_file
from music_analyzer.job_service import JobService
from music_analyzer.job_contracts import job_folder,verify_result,JobError
from music_analyzer.instrumental_restoration import restore

base=project_root();cases=base/'data/ground-truth/cases';root=base/'data/separation';service=JobService(root)
summary=[]
for name,gains in [('vocal-violin',{}),('quiet-vocal-violin',{'lead':.1}),('very-quiet-vocal-violin',{'lead':.01}),
                   ('vocal-quiet-violin',{'strings':.1}),('vocal-no-violin',{'strings':0})]:
    folder=cases/name
    if not (folder/'prepared.json').exists():
        write_json(folder/'case.json',{'name':name,'start_sec':0,'duration_sec':15,
            'reference_sources':{'lead':['../rainfall-40-60/references/lead.wav'],
                'strings':['../../philharmonia/strings-15s.wav']},'reference_gains':gains,
            'scope':'Real voice and violin artificially remixed; explicit quiet voice interference control.'})
        prepare(folder/'case.json')
    prepared=read_json(folder/'prepared.json');asset=ingest_file(Path(prepared['input']),root)
    predictions={}
    for preset in ('vocal_roformer','instrument_mega5'):
        saved=folder/(preset+'-job.json')
        if saved.exists():job=read_json(saved)
        else:
            print(name,preset,'INFERENCE',flush=True)
            while True:
                try:job=service.run(asset.name,preset);break
                except JobError as error:
                    if error.code!='GPU_BUSY':raise
                    time.sleep(2)
            if job['state']!='SUCCEEDED':raise RuntimeError(job)
            write_json(saved,job)
        directory=job_folder(root,job['job_id'])/'result';manifest=verify_result(directory,job)
        predictions[preset]={t['family']:sf.read(directory/t['path'],dtype='float32',always_2d=True)[0] for t in manifest['stems']}
    first=predictions['vocal_roformer'];extra=predictions['instrument_mega5']
    after,inst,moved=restore(first['vocals'],first['instrumental'],[extra[f] for f in ('bowed_strings','brass','synth')])
    mix=sf.read(prepared['input'],dtype='float32',always_2d=True)[0]
    truth=sf.read(prepared['references']['lead']['path'],dtype='float32',always_2d=True)[0]
    strings=sf.read(prepared['references']['strings']['path'],dtype='float32',always_2d=True)[0]
    item={'case':name,'voice_before':score(truth,first['vocals'],mix),'voice_after':score(truth,after,mix),
          'strings_before':score(strings,first['instrumental'],mix),'strings_after':score(strings,inst,mix)}
    for label,audio in [('voice-before',first['vocals']),('voice-after',after),('restored-instrumental',inst)]:sf.write(folder/(label+'.wav'),audio,44100,subtype='FLOAT')
    summary.append(item);write_json(base/'docs/VOCAL_STRING_CONTROL_RESULTS.json',summary)
    print(name,item['voice_before']['raw_sdr_db'],item['voice_after']['raw_sdr_db'],
          item['voice_before']['target_gain'],item['voice_after']['target_gain'],flush=True)
