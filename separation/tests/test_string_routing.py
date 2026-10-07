import numpy as np
from music_analyzer.string_routing import transfer


def tone(freq, n=44100*2):
    t = np.arange(n)/44100
    return np.repeat(np.sin(2*np.pi*freq*t)[:, None], 2, axis=1).astype(np.float32)*.2


def test_violin_evidence_moves_scattered_string_and_preserves_sum():
    violin, pad = tone(440), tone(1500)
    tracks = {'synth': violin*.5+pad, 'other': violin*.3, 'backing': violin*.2}
    zero = np.zeros_like(violin)
    evidence = {'synth': pad, 'bowed_strings': violin, 'brass': zero}
    revised, moved, from_backing = transfer(violin+pad, tracks, evidence)
    np.testing.assert_allclose(sum(revised.values())+moved, sum(tracks.values()), atol=1e-6)
    core = slice(4096, -4096)
    assert np.dot(moved[core, 0], violin[core, 0])/np.dot(violin[core, 0], violin[core, 0]) > .8
    # Pad energy stays in synth because context evidence calls it synth.
    assert abs(np.dot(moved[core, 0], pad[core, 0]))/np.dot(pad[core, 0], pad[core, 0]) < .01
    assert np.abs(from_backing[core]).max() > 0


def test_no_string_evidence_moves_nothing():
    pad = tone(700); zero = np.zeros_like(pad)
    tracks = {'synth': pad, 'other': pad*.1, 'backing': zero}
    revised, moved, _ = transfer(pad*1.1, tracks, {'synth': pad, 'bowed_strings': zero, 'brass': zero})
    assert np.abs(moved).max() < 1e-6


def test_backing_percussion_moves_only_evidenced_percussion():
    from music_analyzer.percussion_refinement import from_backing, RIVALS
    bells, voice = tone(3000), tone(300); zero = np.zeros_like(bells)
    evidence = {'percussion': bells, 'timpani': zero, **{f: zero for f in RIVALS}}
    moved = from_backing(bells+voice, bells*.6+voice, evidence)
    core = slice(4096, -4096)
    assert np.dot(moved[core, 0], bells[core, 0])/np.dot(bells[core, 0], bells[core, 0]) > .5
    assert abs(np.dot(moved[core, 0], voice[core, 0]))/np.dot(voice[core, 0], voice[core, 0]) < .01


def test_context_routing_returns_brass_from_guitar_and_keeps_guitar():
    from music_analyzer.context_routing import transfer, CONTEXT
    horn, gtr = tone(500), tone(2200); zero = np.zeros_like(horn)
    evidence = {h: zero for h in CONTEXT.values()}; evidence['brass'] = horn; evidence['electric-guitar'] = gtr
    moved = transfer(horn+gtr, {'guitar': gtr+horn*.4, 'other': zero}, evidence, 'brass', {'guitar': 1, 'other': 2})
    core = slice(4096, -4096)
    assert np.dot(moved['guitar'][core, 0], horn[core, 0])/np.dot(horn[core, 0], horn[core, 0]) > .3
    assert abs(np.dot(moved['guitar'][core, 0], gtr[core, 0]))/np.dot(gtr[core, 0], gtr[core, 0]) < .01


def test_pad_routing_moves_residual_pad_to_synth_but_leaves_other_music():
    from music_analyzer.context_routing import transfer, CONTEXT
    pad, organ = tone(400), tone(1800); zero = np.zeros_like(pad)
    evidence = {h: zero for h in CONTEXT.values()}; evidence['synth'] = pad
    moved = transfer(pad+organ, {'other': pad*.8+organ, 'strings': zero}, evidence, 'synth', {'other': .15, 'strings': .5})
    core = slice(4096, -4096)
    assert np.dot(moved['other'][core, 0], pad[core, 0])/np.dot(pad[core, 0], pad[core, 0]) > .5
    assert abs(np.dot(moved['other'][core, 0], organ[core, 0]))/np.dot(organ[core, 0], organ[core, 0]) < .01
