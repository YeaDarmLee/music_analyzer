"""Transfer piano leakage supported by an independent contextual drum estimate."""
import numpy as np
from scipy import signal
from scipy.ndimage import median_filter


def cymbal_extract(piano,estimate):
    """Protect harmonic piano bins while transferring supported broadband cymbal bins."""
    piano=np.asarray(piano,dtype=np.float32);estimate=np.asarray(estimate,dtype=np.float32)
    if piano.ndim!=2 or piano.shape[1]!=2 or piano.shape!=estimate.shape or len(piano)<2048:
        raise ValueError('Cymbal timeline mismatch')
    if not np.isfinite(piano).all() or not np.isfinite(estimate).all():raise ValueError('Invalid cymbal audio')
    moved=np.zeros_like(piano)
    for start in range(0,len(piano),512*2048):
        end=min(len(piano),start+512*2048)
        left=max(0,start-8192);right=min(len(piano),end+8192)
        audio=_cymbal_window(piano[left:right],estimate[left:right])
        moved[start:end]=audio[start-left:end-left]
    return moved


def _cymbal_window(piano,estimate):
    spectrum=signal.stft(piano.T,fs=44100,nperseg=2048,noverlap=1536)[2]
    drums=signal.stft(estimate.T,fs=44100,nperseg=2048,noverlap=1536)[2]
    magnitude=np.abs(spectrum)
    harmonic=median_filter(magnitude,size=(1,1,31))
    percussive=median_filter(magnitude,size=(1,31,1))
    total=harmonic**2+percussive**2
    percussion_mask=np.divide(percussive**2,total,out=np.zeros_like(total),where=total>0)**2
    total=np.abs(drums)**2+np.abs(spectrum-drums)**2
    semantic_mask=np.divide(np.abs(drums)**2,total,out=np.zeros_like(total),where=total>0)**2
    frequencies=np.fft.rfftfreq(2048,1/44100)
    high_band=np.clip((frequencies-3000)/2000,0,1)[None,:,None]
    moved=spectrum*percussion_mask*semantic_mask*high_band
    return signal.istft(moved,fs=44100,nperseg=2048,noverlap=1536)[1].T[:len(piano)].astype(np.float32)


def apply(root,row,estimate,manifest):
    from pathlib import Path
    import soundfile as sf
    from .common import read_json,write_json,sha256_file
    from .synth_recovery import settings
    root=Path(root).resolve()
    version,positive,negative,_=settings('cymbal')
    if row.get('cymbal_recovery',{}).get('version')==version:return row
    tracks={t['family']:t for t in row['tracks']}
    meta=read_json(Path(manifest))
    result=meta['results']['part_b']
    if meta['case']['input_sha256']!=sha256_file(root/tracks['piano']['path']):
        raise ValueError('Cymbal recovery input changed')
    if result['positive']!=positive or result['negative']!=negative or result['sha256']!=sha256_file(Path(estimate)):
        raise ValueError('Cymbal recovery provenance mismatch')
    arrays=[]
    for path in (root/tracks['piano']['path'],root/tracks['drums']['path'],Path(estimate)):
        audio,rate=sf.read(path,dtype='float32',always_2d=True)
        if rate!=44100 or audio.ndim!=2 or audio.shape[1]!=2 or not np.isfinite(audio).all():
            raise ValueError('Invalid cymbal recovery audio')
        arrays.append(audio)
    piano,drums,raw=arrays
    if piano.shape!=drums.shape or piano.shape!=raw.shape:raise ValueError('Cymbal timeline mismatch')
    moved=cymbal_extract(piano,raw)
    revised={'piano':piano-moved,'drums':drums+moved}
    error=float(np.max(np.abs(revised['piano'].astype(float)+revised['drums']-piano.astype(float)-drums)))
    if error>2e-7:raise ValueError('Cymbal pair reconstruction failed')
    folder=root/'web'/row['id']
    backup=folder/'record-before-cymbal-recovery-v1.json'
    if not backup.exists():write_json(backup,row)
    updated=[]
    for track in row['tracks']:
        family=track['family']
        if family in revised:
            audio=revised[family]
            path=folder/(family+'-cymbal-refined-v1.wav')
            temporary=path.with_suffix('.partial.wav')
            sf.write(temporary,audio,44100,subtype='FLOAT');temporary.replace(path)
            peak=float(np.abs(audio).max())
            track={k:v for k,v in track.items() if k not in ('silent','signal_rms')}
            track.update(path=str(path.relative_to(root)),sha256=sha256_file(path),peak=peak,
                         over_full_scale=peak>1,derivation='harmonic_protected_cymbal_transfer')
        updated.append(track)
    return {**row,'tracks':updated,'cymbal_recovery':{'version':version,'positive':positive,'negative':negative,
        'manifest':str(Path(manifest).resolve()),'pair_max_abs_error':error,
        'moved_rms':float(np.sqrt(np.mean(moved.astype(float)**2))),
        'original_tracks':{f:tracks[f] for f in ('piano','drums')}}}


def extract(piano, sources, confidence_power=2):
    """Wiener mask from all independent sources; retain phase and stereo timeline."""
    piano=np.asarray(piano,dtype=np.float32)
    if piano.ndim!=2 or piano.shape[1]!=2 or not len(piano) or not np.isfinite(piano).all():
        raise ValueError('Invalid piano timeline')
    if 'drums' not in sources:raise ValueError('Missing independent drums')
    if confidence_power not in (1,2):raise ValueError('Invalid mask confidence power')
    arrays={}
    for family,audio in sources.items():
        audio=np.asarray(audio,dtype=np.float32)
        if audio.shape!=piano.shape or not np.isfinite(audio).all():
            raise ValueError('Independent source timeline mismatch')
        arrays[family]=audio
    if len(piano)<2048:raise ValueError('Piano timeline too short')
    moved=np.zeros_like(piano)
    # Hop-aligned blocks and context keep full-song FFT memory bounded.
    for start in range(0,len(piano),512*2048):
        end=min(len(piano),start+512*2048)
        left=max(0,start-2048);right=min(len(piano),end+2048)
        powers={family:np.abs(signal.stft(audio[left:right].T,fs=44100,nperseg=2048,noverlap=1536)[2])**2
                for family,audio in arrays.items()}
        total=sum(powers.values())
        mask=np.divide(powers['drums'],total,out=np.zeros_like(total),where=total>0)
        mask=mask**confidence_power
        spectrum=signal.stft(piano[left:right].T,fs=44100,nperseg=2048,noverlap=1536)[2]
        audio=signal.istft(spectrum*mask,fs=44100,nperseg=2048,noverlap=1536)[1].T
        moved[start:end]=audio[start-left:end-left]
    return moved
