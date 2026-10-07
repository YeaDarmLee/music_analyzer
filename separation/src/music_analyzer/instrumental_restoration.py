"""Restore instrumental leakage already lost at the initial vocal separation boundary."""
import numpy as np
from scipy import signal


def restore(vocals,instrumental,evidence):
    vocals=np.asarray(vocals,dtype=np.float32);instrumental=np.asarray(instrumental,dtype=np.float32)
    arrays=[np.asarray(a,dtype=np.float32) for a in evidence]
    if not arrays or vocals.ndim!=2 or vocals.shape[1]!=2 or len(vocals)<2048:
        raise ValueError('Invalid restoration timeline')
    if any(a.shape!=vocals.shape or not np.isfinite(a).all() for a in [vocals,instrumental,*arrays]):
        raise ValueError('Restoration source mismatch')
    moved=np.zeros_like(vocals)
    for start in range(0,len(vocals),512*2048):
        end=min(len(vocals),start+512*2048);left=max(0,start-2048);right=min(len(vocals),end+2048)
        v=signal.stft(vocals[left:right].T,fs=44100,nperseg=2048,noverlap=1536)[2]
        estimates=np.stack([signal.stft(a[left:right].T,fs=44100,nperseg=2048,noverlap=1536)[2] for a in arrays])
        selected=np.take_along_axis(estimates,np.argmax(np.abs(estimates),axis=0)[None],axis=0)[0]
        selected_power=np.abs(selected)**2;vocal_power=np.abs(v)**2
        total=selected_power+np.abs(v-selected)**2
        confidence=np.divide(selected_power,total,out=np.zeros_like(total),where=total>0)**3
        compatible=np.divide(vocal_power,selected_power,out=np.zeros_like(total),where=selected_power>0)
        confidence*=np.minimum(compatible,1)
        coherence=np.divide(np.real(v*selected.conj()),np.abs(v)*np.abs(selected),out=np.zeros_like(total),where=np.abs(v)*np.abs(selected)>0)
        confidence*=np.clip(coherence,0,1)**2
        audio=signal.istft(v*confidence,fs=44100,nperseg=2048,noverlap=1536)[1].T
        moved[start:end]=audio[start-left:end-left]
    return vocals-moved,instrumental+moved,moved


def apply(root,row,first_dir,first,context_dir,context):
    from pathlib import Path
    import soundfile as sf
    from .common import sha256_file
    root=Path(root);first_dir=Path(first_dir);context_dir=Path(context_dir)
    source={t['family']:t for t in first['stems']}
    def read(path):
        audio,rate=sf.read(path,dtype='float32',always_2d=True)
        if rate!=44100:raise ValueError('Restoration sample rate mismatch')
        return audio
    vocals=read(first_dir/source['vocals']['path']);instrumental=read(first_dir/source['instrumental']['path'])
    estimates={t['family']:read(context_dir/t['path']) for t in context['stems']}
    after_vocals,after_instrumental,moved=restore(vocals,instrumental,
        [estimates[f] for f in ('bowed_strings','brass','synth')])
    error=float(np.max(np.abs(vocals.astype(float)+instrumental-after_vocals.astype(float)-after_instrumental)))
    if error>2e-7:raise ValueError('Restoration pair reconstruction failed')
    folder=root/'web'/row['id'];folder.mkdir(parents=True,exist_ok=True)
    revised=[]
    for track in first['stems']:
        family=track['family']
        if family in ('vocals','instrumental'):
            audio=after_vocals if family=='vocals' else after_instrumental
            path=folder/(family+'-context-restored-v1.wav');temporary=path.with_suffix('.partial.wav')
            sf.write(temporary,audio,44100,subtype='FLOAT');temporary.replace(path)
            peak=float(np.abs(audio).max())
            track={**track,'path':str(path.resolve()),'sha256':sha256_file(path),'peak':peak,
                   'over_full_scale':peak>1,'derivation':'instrument_evidence_vocal_restoration'}
        revised.append(track)
    row={**row,'vocal_instrument_restoration':{'version':'context-restoration-v1','pair_max_abs_error':error,
        'moved_rms':float(np.sqrt(np.mean(moved.astype(float)**2))),
        'original_tracks':{family:{**source[family],'path':str((first_dir/source[family]['path']).relative_to(root))} for family in ('vocals','instrumental')}}}
    return row,{**first,'stems':revised}
