"""Add only independently supported missing tonal material from the residual."""
import numpy as np
from scipy import signal


def recover(other,tracks,evidence):
    families=('synth','strings','brass')
    arrays=[np.asarray(a,dtype=np.float32) for a in [other,*[tracks[f] for f in families],*[evidence[f] for f in families]]]
    if len(arrays[0])<2048 or any(a.shape!=arrays[0].shape or a.ndim!=2 or a.shape[1]!=2 or not np.isfinite(a).all() for a in arrays):
        raise ValueError('Tonal recovery timeline mismatch')
    recovered={f:np.zeros_like(arrays[0]) for f in families}
    for start in range(0,len(other),512*2048):
        end=min(len(other),start+512*2048);left=max(0,start-2048);right=min(len(other),end+2048)
        spectra=[signal.stft(a[left:right].T,nperseg=2048,noverlap=1536)[2] for a in arrays]
        residual=spectra[0]
        missing=np.stack([spectra[4+i]-spectra[1+i] for i in range(3)])
        power=np.abs(missing)**2
        total=power+np.abs(residual[None]-missing)**2
        masks=np.divide(power,total,out=np.zeros_like(power),where=total>0)**6
        denominator=np.abs(residual[None])*np.abs(missing)
        coherence=np.divide(np.real(residual[None]*missing.conj()),denominator,out=np.zeros_like(power),where=denominator>0)
        masks*=np.clip(coherence,0,1)**2
        winner=np.argmax(masks,axis=0)
        for i,family in enumerate(families):
            if family=='synth':continue
            spectrum=residual*masks[i]*(winner==i)
            audio=signal.istft(spectrum,nperseg=2048,noverlap=1536)[1].T
            recovered[family][start:end]=audio[start-left:end-left]
    return {f:tracks[f]+recovered[f] for f in families},other-sum(recovered.values())
