"""Conservative percussion routing from existing drums and unclassified accompaniment."""
import numpy as np
from scipy import signal


def transfer(drums,other,estimate,*additional):
    arrays=[np.asarray(a,dtype=np.float32) for a in (drums,other,estimate,*additional)]
    if any(a.ndim!=2 or a.shape[1]!=2 or a.shape!=arrays[0].shape or not np.isfinite(a).all() for a in arrays) or len(arrays[0])<2048:
        raise ValueError('Percussion timeline mismatch')
    drums,other=arrays[:2]
    moved=np.zeros_like(drums);from_drums=np.zeros_like(drums)
    for start in range(0,len(drums),512*2048):
        end=min(len(drums),start+512*2048);left=max(0,start-2048);right=min(len(drums),end+2048)
        spectra=[signal.stft(a[left:right].T,fs=44100,nperseg=2048,noverlap=1536)[2] for a in arrays]
        drum,remaining=spectra[:2];source=drum+remaining
        candidates=np.stack(spectra[2:])
        evidence=np.take_along_axis(candidates,np.argmax(np.abs(candidates),axis=0)[None],axis=0)[0]
        power=np.abs(evidence)**2+np.abs(source-evidence)**2
        confidence=np.divide(np.abs(evidence)**2,power,out=np.zeros_like(power),where=power>0)**2
        percussion=source*confidence
        ownership=np.abs(drum)**2+np.abs(remaining)**2
        drum_share=np.divide(np.abs(drum)**2,ownership,out=np.zeros_like(ownership),where=ownership>0)
        for target,spectrum in ((moved,percussion),(from_drums,percussion*drum_share)):
            audio=signal.istft(spectrum,fs=44100,nperseg=2048,noverlap=1536)[1].T
            target[start:end]=audio[start-left:end-left]
    return drums-from_drums,other-(moved-from_drums),moved


def prepare_source(root,row):
    from pathlib import Path
    import soundfile as sf
    root=Path(root);tracks={t['family']:t for t in row['tracks']};arrays=[]
    for f in ('drums','other'):
        audio,rate=sf.read(root/tracks[f]['path'],dtype='float32',always_2d=True)
        if rate!=44100:raise ValueError('Percussion source rate mismatch')
        arrays.append(audio)
    if arrays[0].shape!=arrays[1].shape or arrays[0].ndim!=2 or arrays[0].shape[1]!=2 or not all(np.isfinite(a).all() for a in arrays):
        raise ValueError('Percussion source timeline mismatch')
    folder=root/'web'/row['id'];folder.mkdir(parents=True,exist_ok=True)
    path=folder/'percussion-source-v2.wav';temporary=path.with_suffix('.partial.wav')
    sf.write(temporary,arrays[0]+arrays[1],44100,subtype='FLOAT');temporary.replace(path)
    return path


def apply(root,row,estimate,job_id,additional=(),version='context-supported-percussion-v1'):
    from pathlib import Path
    import soundfile as sf
    from .common import sha256_file
    root=Path(root);source={t['family']:t for t in row['tracks']}
    if row.get('percussion_refinement'):
        if row['percussion_refinement']['version']==version:return row
        raise ValueError('Different percussion version requires the original unrefined tracks')
    arrays=[]
    for path in (root/source['drums']['path'],root/source['other']['path'],Path(estimate),*map(Path,additional)):
        audio,rate=sf.read(path,dtype='float32',always_2d=True)
        if rate!=44100:raise ValueError('Percussion rate mismatch')
        arrays.append(audio)
    drums,other=arrays[:2]
    after_drums,after_other,percussion=transfer(*arrays)
    error=float(np.max(np.abs(drums.astype(float)+other-after_drums.astype(float)-after_other-percussion)))
    if error>2e-6:raise ValueError('Percussion partition reconstruction failed')
    folder=root/'web'/row['id'];folder.mkdir(parents=True,exist_ok=True);tracks=[]
    revised={'drums':after_drums,'other':after_other,'percussion':percussion}
    for track in [*row['tracks'],{'id':'stem_percussion','family':'percussion','canonical_id':'instrument.percussion','display_name':'기타 타악기','quality_score':None}]:
        family=track['family']
        if family in revised:
            audio=revised[family];path=folder/(family+'-percussion-routed-v1.wav');temporary=path.with_suffix('.partial.wav')
            sf.write(temporary,audio,44100,subtype='FLOAT');temporary.replace(path)
            peak=float(np.abs(audio).max())
            track={k:v for k,v in track.items() if k not in ('silent','signal_rms')}
            track.update(path=str(path.relative_to(root)),sha256=sha256_file(path),peak=peak,
                over_full_scale=peak>1,derivation='context_supported_percussion_routing',sample_rate=44100,
                channels=2,num_frames=len(audio),subtype='FLOAT',presence='unknown')
        tracks.append(track)
    return {**row,'tracks':tracks,'percussion_refinement':{'version':version,
        'context_job_id':job_id,'estimate_sha256':[sha256_file(Path(p)) for p in (estimate,*additional)],'partition_max_abs_error':error,
        'original_tracks':{f:source[f] for f in ('drums','other')}}}


RIVALS=('synth','bowed_strings','brass','acoustic-guitar','electric-guitar')


def from_backing(mixture,backing,evidence):
    """Percussion the vocal separator took into backing; context ownership times phase agreement."""
    arrays=[np.asarray(a,dtype=np.float32) for a in (mixture,backing,evidence['percussion']+evidence['timpani'],*(evidence[f] for f in RIVALS))]
    if any(a.ndim!=2 or a.shape[1]!=2 or a.shape!=arrays[0].shape or not np.isfinite(a).all() for a in arrays) or len(arrays[0])<2048:
        raise ValueError('Backing percussion timeline mismatch')
    n=len(arrays[0]);moved=np.zeros_like(arrays[0])
    for start in range(0,n,512*2048):
        end=min(n,start+512*2048);left=max(0,start-2048);right=min(n,end+2048)
        X,S,P,*rivals=[signal.stft(a[left:right].T,fs=44100,nperseg=2048,noverlap=1536)[2] for a in arrays]
        power=np.abs(P)**2+sum(np.abs(r)**2 for r in rivals)+np.abs(X-P-sum(rivals))**2
        share=np.divide(np.abs(P)**2,power,out=np.zeros(power.shape),where=power>0)
        d=np.abs(S)*np.abs(P);coherence=np.divide(np.real(S*P.conj()),d,out=np.zeros(d.shape),where=d>0)
        audio=signal.istft(S*share*np.clip(coherence,0,1)**2,fs=44100,nperseg=2048,noverlap=1536)[1].T
        moved[start:end]=audio[start-left:end-left]
    return moved


def apply_backing(root,row,evidence,job_id,version='backing-percussion-v1'):
    """Move backing-held percussion into percussion; the moved audio also joins the instrumental."""
    from pathlib import Path
    import soundfile as sf
    from .common import sha256_file
    root=Path(root);source={t['family']:t for t in row['tracks']}
    if row.get('backing_percussion'):
        if row['backing_percussion']['version']==version:return row
        raise ValueError('Different backing percussion version requires the original tracks')
    def read(path):
        audio,rate=sf.read(path,dtype='float32',always_2d=True)
        if rate!=44100:raise ValueError('Backing percussion rate mismatch')
        return audio
    backing,percussion,instrumental=(read(root/p) for p in (source['backing']['path'],source['percussion']['path'],row['instrumental']))
    moved=from_backing(read(root/row['original']),backing,{f:read(Path(p)) for f,p in evidence.items()})
    revised={'backing':backing-moved,'percussion':percussion+moved}
    error=float(np.max(np.abs(backing.astype(float)+percussion-revised['backing']-revised['percussion'])))
    if error>2e-6:raise ValueError('Backing percussion partition reconstruction failed')
    folder=root/'web'/row['id'];folder.mkdir(parents=True,exist_ok=True)
    def write(name,audio):
        path=folder/name;temporary=path.with_suffix('.partial.wav')
        sf.write(temporary,audio,44100,subtype='FLOAT');temporary.replace(path);return path
    tracks=[]
    for track in row['tracks']:
        if track['family'] in revised:
            audio=revised[track['family']];path=write(track['family']+'-backing-percussion-v1.wav',audio);peak=float(np.abs(audio).max())
            track={k:v for k,v in track.items() if k not in ('silent','signal_rms')}
            track.update(path=str(path.relative_to(root)),sha256=sha256_file(path),peak=peak,over_full_scale=peak>1,derivation='backing_percussion_routing')
        tracks.append(track)
    path=write('instrumental-backing-percussion-v1.wav',instrumental+moved)
    return {**row,'tracks':tracks,'instrumental':str(path.relative_to(root)),'backing_percussion':{'version':version,'context_job_id':job_id,
        'partition_max_abs_error':error,'moved_rms':float(np.sqrt(np.mean(moved.astype(float)**2))),
        'original_tracks':{f:source[f] for f in revised},'original_instrumental':row['instrumental']}}
