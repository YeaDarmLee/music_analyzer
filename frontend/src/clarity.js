// Gentle, instrument-specific starting points; strength 0 is exactly bypassed.
export const profiles={
 vocals:[[300,-1.5,.8],[3200,1.3,.7]],guitar:[[320,-1.4,.8],[2600,1.2,.7]],
 piano:[[280,-1.2,.8],[3000,1,.7]],bass:[[300,-.7,.8],[1200,.6,.7]],
 drums:[[350,-.8,.8],[4500,.8,.7]],other:[[350,-.6,.7],[3000,.5,.7]]
};
profiles.brass=profiles.other;profiles.synth=profiles.other;profiles.strings=profiles.other;profiles.acoustic_guitar=profiles.guitar;profiles.lead=profiles.vocals;profiles.backing=profiles.vocals;profiles.synth_pad=profiles.other;profiles.other_residual=profiles.other;profiles.lead_guitar=profiles.guitar;profiles.guitar_residual=profiles.guitar;
export function filters(context,family){return (profiles[family]||[]).map(([frequency,gain,q])=>{const node=context.createBiquadFilter();node.type='peaking';node.frequency.value=frequency;node.Q.value=q;node.gain.value=0;return {node,gain}})}
export function updateFilters(chain,enabled,strength,context){for(const f of chain)f.node.gain.setTargetAtTime(enabled?f.gain*strength/50:0,context.currentTime,.025)}
