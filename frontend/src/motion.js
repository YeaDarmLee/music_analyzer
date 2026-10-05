const ease='cubic-bezier(.22,.75,.18,1)';
const reduced=()=>matchMedia('(prefers-reduced-motion: reduce)').matches;
const presses=new WeakMap();
let pending=new Set();
export async function settled(){while(pending.size)await Promise.allSettled([...pending])}
function animate(target,frames,duration,done){
 target.style.willChange='transform, opacity';
 const animation=target.animate(frames,{duration:reduced()?0:duration,easing:ease,fill:'both'});
 const task=animation.finished.catch(()=>{}).then(()=>{pending.delete(task);done?.();animation.cancel();target.style.willChange=''});pending.add(task);return task;
}
export function originOf(event){const node=event?.currentTarget;if(!(node instanceof HTMLElement))return null;presses.get(node)?.cancel();return {rect:node.getBoundingClientRect(),node:node.cloneNode(true)}}
export function expand(target,origin,done){
 if(reduced()||!origin)return animate(target,[{transform:'translate3d(0,12px,0) scale(.99)',opacity:.65},{transform:'translate3d(0,0,0) scale(1)',opacity:1}],340,done);
 const from=origin.rect,to=target.getBoundingClientRect();
 const dx=from.left+from.width/2-to.left-to.width/2,dy=from.top+from.height/2-to.top-to.height/2;
 const sx=Math.max(.03,from.width/to.width),sy=Math.max(.03,from.height/to.height);
 const start=`translate3d(${dx}px,${dy}px,0) scale(${sx},${sy})`;
 const shell=document.createElement('div');shell.className='motion-shell';shell.setAttribute('aria-hidden','true');
 Object.assign(shell.style,{left:to.left+'px',top:to.top+'px',width:to.width+'px',height:to.height+'px'});document.body.append(shell);
 // The shell's geometry is fixed. Only compositor properties change each frame.
 animate(shell,[{transform:start,opacity:1},{transform:'translate3d(0,0,0) scale(1)',opacity:0}],520,()=>shell.remove());
 return animate(target,[{transform:start,opacity:0},{transform:'translate3d(0,0,0) scale(1)',opacity:1}],520,done);
}
export function collapse(target,origin,done){
 const to=origin?.rect,from=target.getBoundingClientRect();
 const end=to?{transform:`translate3d(${to.left+to.width/2-from.left-from.width/2}px,${to.top+to.height/2-from.top-from.height/2}px,0) scale(${Math.max(.03,to.width/from.width)},${Math.max(.03,to.height/from.height)})`,opacity:0}:{transform:'translate3d(0,-8px,0) scale(.995)',opacity:0};
 return animate(target,[{transform:'translate3d(0,0,0) scale(1)',opacity:1},end],to?380:130,done);
}
export function press(event){
 if(reduced())return;const target=event.target.closest('button,a');if(!target||target.disabled)return;
 presses.get(target)?.cancel();
 const animation=target.animate([{transform:'scale(1)'},{transform:'scale(.975)',offset:.35},{transform:'scale(1)'}],{duration:220,easing:ease});presses.set(target,animation);
}
