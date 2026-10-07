<script setup>
import {ref,computed,onMounted,onBeforeUnmount,nextTick} from 'vue';
import {Drum} from '@lucide/vue';
import {mdiMicrophone,mdiPiano,mdiGuitarElectric,mdiWaveform,mdiDisc} from '@mdi/js';
const icons={vocals:mdiMicrophone,piano:mdiPiano,guitar:mdiGuitarElectric,bass:mdiGuitarElectric,other:mdiWaveform,original:mdiDisc};
const m=ref(null),pos=ref(0),playing=ref(false),busy=ref(false),master=ref(1),root=ref(null);
const mute=ref({}),solo=ref({}),vol=ref({});
let ctx,out,bufs={},gains={},srcs=[],t0=0,raf=0,ro;
const rows=computed(()=>m.value?[{key:'original',name:'원곡',color:'#c7ccd9',...m.value.original},...m.value.tracks]:[]);
const parts=computed(()=>rows.value.filter(r=>r.key!=='original'));
const ticks=computed(()=>{const d=m.value?.duration||0,step=[1,2,5,10,15,20,30].find(n=>d/n<=12)||60,o=[];for(let t=0;t<d;t+=step)o.push({t,left:t/d*100});return o});
const anySolo=computed(()=>Object.values(solo.value).some(Boolean));
const audible=k=>anySolo.value?!!solo.value[k]:!mute.value[k];
const level=k=>audible(k)?(vol.value[k]??1):0;
const allMuted=computed(()=>parts.value.every(r=>mute.value[r.key])),anyMuted=computed(()=>parts.value.some(r=>mute.value[r.key]));
const allSolo=computed(()=>parts.value.every(r=>solo.value[r.key])),anySoloP=computed(()=>parts.value.some(r=>solo.value[r.key]));
function apply(){if(!ctx)return;rows.value.forEach(r=>gains[r.key]&&(gains[r.key].gain.value=level(r.key)));out.gain.value=master.value}
const flip=(kind,k)=>{const map=kind==='m'?mute:solo;map.value={...map.value,[k]:!map.value[k]};apply()};
function masterToggle(kind,any){const map=kind==='m'?mute:solo;const next={...map.value};parts.value.forEach(r=>next[r.key]=!any);map.value=next;apply()}
function setVol(k,v){vol.value={...vol.value,[k]:v};apply()}
function resetVolumes(){vol.value={};master.value=1;apply()}
async function load(){
  ctx=new AudioContext();out=ctx.createGain();out.connect(ctx.destination);
  await Promise.all(rows.value.map(async r=>{bufs[r.key]=await ctx.decodeAudioData(await (await fetch(r.file)).arrayBuffer());const g=ctx.createGain();g.connect(out);gains[r.key]=g}));
  apply();
}
function stopSources(){srcs.forEach(s=>{try{s.stop()}catch{}});srcs=[]}
function tick(){pos.value=Math.min(m.value.duration,ctx.currentTime-t0);if(pos.value>=m.value.duration)return stop(true);raf=requestAnimationFrame(tick)}
async function play(){
  if(!ctx){busy.value=true;try{await load()}finally{busy.value=false}}
  await ctx.resume();
  if(pos.value>=m.value.duration-.05)pos.value=0;
  srcs=rows.value.map(r=>{const s=ctx.createBufferSource();s.buffer=bufs[r.key];s.connect(gains[r.key]);s.start(0,pos.value);return s});
  t0=ctx.currentTime-pos.value;playing.value=true;tick();
}
function stop(reset){cancelAnimationFrame(raf);stopSources();playing.value=false;if(reset)pos.value=0}
const toggle=()=>{if(!busy.value)playing.value?stop():play()};
function seekTo(p){const was=playing.value;stop();pos.value=p;if(was)play()}
const seekWave=e=>{const r=e.currentTarget.getBoundingClientRect();seekTo(Math.max(0,Math.min(1,(e.clientX-r.left)/r.width))*m.value.duration)};
const stamp=s=>Math.floor(s/60)+':'+String(Math.floor(s%60)).padStart(2,'0');
function draw(){root.value?.querySelectorAll('canvas[data-wave]').forEach(c=>{const r=rows.value.find(r=>r.key===c.dataset.wave);if(!r)return;const w=Math.max(300,c.clientWidth),h=c.clientHeight,d=devicePixelRatio||1;c.width=w*d;c.height=h*d;const x=c.getContext('2d');x.scale(d,d);x.fillStyle=r.color;x.globalAlpha=.75;const peak=Math.max(.02,...r.peaks);for(let i=0;i<w;i+=3){const v=r.peaks[Math.floor(i/w*r.peaks.length)]||0,H=Math.max(1,v/peak*(h-12));x.fillRect(i,(h-H)/2,1.5,H)}})}
onMounted(async()=>{m.value=await (await fetch('/samples/manifest.json')).json();mute.value={original:true};await nextTick();draw();ro=new ResizeObserver(draw);ro.observe(root.value)});
onBeforeUnmount(()=>{stop();ro?.disconnect();ctx?.close()});
</script>
<template>
<div v-if="m" ref="root" class="sp-wrap session">
<div class="transport master-row"><div class="master-left"><span class="master-label">전체</span><button :class="{selected:allMuted,partial:anyMuted&&!allMuted}" aria-label="전체 음소거" @click="masterToggle('m',anyMuted)" :title="anyMuted?'눌려 있는 음소거를 모두 해제':'모든 트랙 음소거'">M</button><button :class="{selected:allSolo,partial:anySoloP&&!allSolo}" aria-label="전체 솔로" @click="masterToggle('s',anySoloP)" :title="anySoloP?'눌려 있는 솔로를 모두 해제':'모든 트랙 솔로'">S</button></div>
<div class="master-main"><div class="play-controls"><button class="reset" aria-label="처음으로" @click="stop();pos=0">↤</button><button class="play" :aria-label="playing?'일시정지':'재생'" @click="toggle">{{busy?'◌':playing?'Ⅱ':'▶'}}</button><button class="reset" aria-label="모든 볼륨 기본값으로" title="모든 볼륨 기본값으로" @click="resetVolumes">↻</button><div class="time"><strong>{{stamp(pos)}}</strong><span>/ {{stamp(m.duration)}}</span></div></div>
<div class="transport-right"><label class="master">마스터<input v-model.number="master" type="range" min="0" max="2" step=".01" @input="apply" @dblclick="master=1;apply()" title="더블클릭하여 기본 음량(100%)으로 복원" aria-label="마스터 음량"><span>{{Math.round(master*100)}}%</span></label></div></div><span></span></div>
<div class="daw"><div class="daw-ruler"><span>TRACKS <b>{{parts.length}}</b></span><div class="ruler-scale"><i v-for="t in ticks" :key="t.t" :style="{left:t.left+'%'}">{{t.t}}s</i><input class="timeline" type="range" :value="pos" min="0" :max="m.duration" step=".1" @input="seekTo(+$event.target.value)" aria-label="재생 위치"><div class="ruler-head" :style="{left:pos/m.duration*100+'%'}"></div></div><span></span></div>
<div v-for="(r,i) in rows" :key="r.key" class="track-row" :style="{'--track':r.color,'--index':i}" :class="{muted:!audible(r.key)}">
<div class="track-info"><div class="track-title"><span class="track-icon" aria-hidden="true"><Drum v-if="r.key==='drums'" :size="22" :stroke-width="1.8"/><svg v-else viewBox="0 0 24 24"><path :d="icons[r.key]||mdiWaveform"/></svg></span><b>{{r.name}}</b><span class="track-format">{{r.key==='original'?'REF':'MP3'}}</span></div>
<div class="track-settings"><button :class="{selected:mute[r.key]}" :aria-label="r.name+' 음소거'" :aria-pressed="!!mute[r.key]" @click="flip('m',r.key)">M</button><button :class="{selected:solo[r.key]}" :aria-label="r.name+' 솔로'" :aria-pressed="!!solo[r.key]" @click="flip('s',r.key)">S</button><input type="range" min="0" max="2" step=".01" :value="vol[r.key]??1" @input="setVol(r.key,+$event.target.value)" @dblclick="setVol(r.key,1)" title="더블클릭하여 기본 음량(100%)으로 복원" :aria-label="r.name+' 음량'"><span>{{Math.round((vol[r.key]??1)*100)}}%</span></div></div>
<div class="waveform" @click="seekWave"><canvas :data-wave="r.key"></canvas><div class="playhead" :style="{left:pos/m.duration*100+'%'}"></div></div><span></span></div>
</div>
<p class="sp-note">Mureka AI로 직접 만든 음원이라 저작권 문제가 없는 샘플이에요. 이 곡의 45초 구간을 6트랙으로 분리한 결과입니다.</p>
</div>
</template>
