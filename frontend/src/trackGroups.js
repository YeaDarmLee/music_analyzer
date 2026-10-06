export function trackLevels(tracks, expanded) {
 const parents=new Map(tracks.filter(t=>!t.parent_family).map(t=>[t.family,t]));
 const eligible=t=>t.parent_family?!!expanded[t.parent_family]:!expanded[t.family];
 const solo=tracks.some(t=>t.solo&&(eligible(t)||expanded[t.family]));
 return new Map(tracks.map(t=>{
  const parent=t.parent_family?parents.get(t.parent_family):null;
  const selected=t.solo||parent?.solo;
  const audible=eligible(t)&&((!t.mute&&!parent?.mute)||selected)&&(!solo||selected);
  return [t.family,audible?t.volume*(parent?.volume??1):0];
 }));
}
