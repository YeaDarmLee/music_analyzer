"""Local experimental reference-conditioned voice extraction; speech-to-singing transfer unverified."""
import sys,types,json,time,hashlib
from pathlib import Path
from uuid import uuid4
import numpy as np,soundfile as sf,torch,yaml,torchaudio
from scipy.signal import resample_poly
from filelock import FileLock
from music_analyzer.common import project_root,write_json,sha256_file
from music_analyzer.roformer_runner import overlap_infer
root=project_root()/'data/separation';tools=root/'tools/wesep-reference';out=root/'vocal-comparisons/identity-reference-223'
rev='f0e479e998206a5404feb4f735113ff9bf6c4d55';spkrev='e9bbf73d0fd13db6cf42a6cb2eafb0d7dd0f8e0e'
# Import only official architecture modules; avoid training and web CLI dependencies.
def package(name,path):
 m=types.ModuleType(name);m.__path__=[str(path)];sys.modules[name]=m
 if '.' in name:
  parent,child=name.rsplit('.',1);setattr(sys.modules[parent],child,m)
 return m
for name,base in [('wesep',tools/('wesep-'+rev)/'wesep'),('wespeaker',tools/('wespeaker-'+spkrev)/'wespeaker')]:
 package(name,base);package(name+'.models',base/'models')
from wespeaker.models.ecapa_tdnn import ECAPA_TDNN_GLOB_c512
selector=types.ModuleType('wespeaker.models.speaker_model')
def select(name):
 if name!='ECAPA_TDNN_GLOB_c512':raise ValueError('Unexpected speaker architecture')
 return ECAPA_TDNN_GLOB_c512
selector.get_speaker_model=select;sys.modules[selector.__name__]=selector
from wesep.models.bsrnn import BSRNN
config=yaml.safe_load((tools/'checkpoint/config.yaml').read_text())
args=config['model_args']['tse_model'];args['spk_model_init']=False
provenance={'wesep_revision':rev,'wespeaker_revision':spkrev,'checkpoint_sha256':sha256_file(tools/'checkpoint/avg_model.pt'),'code_license':'Apache-2.0','weight_license':'UNRESOLVED','native_rate':16000,'quality_improvement_verified':False,'training_domain':'speech; singing transfer unverified','adapter':'official BSRNN/ECAPA architecture only; no VAD/output normalization; no modified learned weights','files':{}}
for repo in (tools/('wesep-'+rev),tools/('wespeaker-'+spkrev)):
 for file in repo.rglob('*.py'):provenance['files'][str(file.relative_to(tools))]=sha256_file(file)
write_json(out/'wesep-provenance.json',provenance)
with FileLock(str(root/'runtime/supervisor.lock'),timeout=0),FileLock(str(root/'runtime/gpu-execution.lock'),timeout=0):
 torch.manual_seed(0);model=BSRNN(**args)
 weights=torch.load(tools/'checkpoint/avg_model.pt',map_location='cpu',weights_only=True)['models'][0]
 weights={k.removeprefix('module.'):v for k,v in weights.items()}
 model.load_state_dict(weights,strict=True);model.eval().to('cuda');del weights
 reference,rate=sf.read(out/'lead_reference_short.wav',dtype='float32',always_2d=True)
 reference=resample_poly(reference.mean(axis=1),160,441).astype(np.float32)
 enroll=torch.from_numpy(reference).unsqueeze(0)
 feat=torchaudio.compliance.kaldi.fbank(enroll,num_mel_bins=80,frame_length=25,frame_shift=10,sample_frequency=16000,dither=0)
 feat=(feat-feat.mean(0)).unsqueeze(0).to('cuda')
 for input_name,label,start in [('unison_test','3:43–4:13 기준 음성 후보',223),('lead_only_control','1:10–1:40 단독 보컬 대조',70)]:
  audio,rate=sf.read(out/(input_name+'.wav'),dtype='float32',always_2d=True)
  native=resample_poly(audio,160,441,axis=0).astype(np.float32)
  def infer(piece):
   with torch.inference_mode():
    results=[]
    for channel in piece:
     estimate=model(torch.from_numpy(channel.copy()).unsqueeze(0).to('cuda'),feat)[0]
     results.append(estimate.detach().cpu().numpy().reshape(-1))
    return np.stack(results)
  ticks=[0]
  def tick():ticks[0]+=1;print('CHUNK',input_name,ticks[0],flush=True)
  estimate=overlap_infer(native.T,160000,.5,infer,tick=tick)
  lead=resample_poly(estimate.T,441,160,axis=0).astype(np.float32)[:len(audio)]
  if lead.shape!=audio.shape or not np.isfinite(lead).all():raise ValueError('Invalid result')
  residual=audio-lead
  folder=out/input_name;folder.mkdir(exist_ok=True)
  stems=[]
  for family,samples in [('lead',lead),('backing',residual)]:
   path=folder/(family+'.wav');sf.write(path,samples,44100,subtype='FLOAT');stems.append({'family':family,'path':str(path.relative_to(root)),'sha256':sha256_file(path),'peak':float(np.abs(samples).max()),'derivation':'reference_conditioned_estimate' if family=='lead' else 'input_minus_target_estimate'})
  row={'id':'analysis_'+uuid4().hex,'name':'주님의 선하심 · WeSep · '+label,'state':'SUCCEEDED','stage':'기준 음성 실험 완료 · 청취 검증 필요','progress':100,'created':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'model':'wesep_reference_experimental','duration':len(audio)/44100,'tracks':stems,'original':str((out/(input_name+'.wav')).relative_to(root)),'job_ids':[],'source_start_sec':start,'reference_range_sec':[45,60],'quality_improvement_verified':False,'native_model_rate':16000,'provenance':str((out/'wesep-provenance.json').relative_to(root))}
  write_json(root/'web'/row['id']/'record.json',row);write_json(folder/'manifest.json',row)
  print('RESULT',row['id'],flush=True)
