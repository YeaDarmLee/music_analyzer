<script setup>
import {ref,computed,onMounted,onBeforeUnmount} from 'vue';
const m=ref(null),pos=ref(0),playing=ref(false),busy=ref(false);
const mute=ref({}),solo=ref({});
let ctx,bufs={},gains={},srcs=[],t0=0,raf=0;
const rows=computed(()=>m.value?[{key:'original',name:'원곡',color:'#c7ccd9',...m.value.original},...m.value.tracks]:[]);
const audible=k=>{const s=Object.values(solo.value).some(Boolean);return s?!!solo.value[k]:!mute.value[k]};
const apply=()=>rows.value.forEach(r=>{if(gains[r.key])gains[r.key].gain.value=audible(r.key)?1:0});
function toggle(kind,k){const map=kind==='m'?mute:solo;map.value={...map.value,[k]:!map.value[k]};apply()}
async function load(){
  ctx=new AudioContext();
  await Promise.all(rows.value.map(async r=>{bufs[r.key]=await ctx.decodeAudioData(await (await fetch(r.file)).arrayBuffer());const g=ctx.createGain();g.connect(ctx.destination);gains[r.key]=g}));
  apply();
}
function stopSources(){srcs.forEach(s=>{s.onended=null;try{s.stop()}catch{}});srcs=[]}
function tick(){pos.value=Math.min(m.value.duration,ctx.currentTime-t0);if(pos.value>=m.value.duration)return stop(true);raf=requestAnimationFrame(tick)}
async function play(){
  if(!ctx){busy.value=true;try{await load()}finally{busy.value=false}}
  await ctx.resume();
  if(pos.value>=m.value.duration-.05)pos.value=0;
  srcs=rows.value.map(r=>{const s=ctx.createBufferSource();s.buffer=bufs[r.key];s.connect(gains[r.key]);s.start(0,pos.value);return s});
  t0=ctx.currentTime-pos.value;playing.value=true;tick();
}
function stop(reset){cancelAnimationFrame(raf);stopSources();playing.value=false;if(reset)pos.value=0}
function toggleP(){if(busy.value)return;playing.value?stop():play()}
function seek(e){const r=e.currentTarget.getBoundingClientRect();const p=Math.max(0,Math.min(1,(e.clientX-r.left)/r.width))*m.value.duration;const was=playing.value;stop();pos.value=p;if(was)play()}
const stamp=s=>Math.floor(s/60)+':'+String(Math.floor(s%60)).padStart(2,'0');
onMounted(async()=>{m.value=await (await fetch('/samples/manifest.json')).json();mute.value={original:true}});
onBeforeUnmount(()=>{stop();ctx?.close()});
</script>
<template>
<div v-if="m" class="sp">
<div class="sp-bar"><button class="sp-play" :aria-label="playing?'일시정지':'재생'" @click="toggleP">{{busy?'◌':playing?'Ⅱ':'▶'}}</button><span class="sp-time"><b>{{stamp(pos)}}</b> / {{stamp(m.duration)}}</span><span class="sp-hint">M 음소거 · S 솔로 — 원곡은 기본 음소거예요</span></div>
<div v-for="r in rows" :key="r.key" class="sp-row" :class="{off:!audible(r.key)}" :style="{'--c':r.color}">
<div class="sp-info"><b>{{r.name}}</b><div><button :class="{on:mute[r.key]}" :aria-pressed="!!mute[r.key]" :aria-label="r.name+' 음소거'" @click="toggle('m',r.key)">M</button><button :class="{on:solo[r.key]}" :aria-pressed="!!solo[r.key]" :aria-label="r.name+' 솔로'" @click="toggle('s',r.key)">S</button></div></div>
<div class="sp-wave" @click="seek"><i v-for="(p,n) in r.peaks" :key="n" :style="{height:Math.max(3,p*100)+'%'}"></i><span class="sp-head" :style="{left:pos/m.duration*100+'%'}"></span></div>
</div>
<p class="sp-note">Mureka AI로 직접 만든 음원이라 저작권 문제가 없는 샘플이에요. 이 곡의 45초 구간을 6트랙으로 분리한 결과입니다.</p>
</div>
</template>
