<script setup>
import {ref,computed,onMounted,onBeforeUnmount,nextTick} from 'vue';
import {filters,updateFilters} from './clarity';
import {originOf,expand,collapse,press,settled} from './motion';
let modalOrigin,pageOrigin;
function modalEnter(el,done){el.animate([{opacity:0},{opacity:1}],{duration:420,easing:'cubic-bezier(.22,.75,.18,1)'});expand(el.querySelector('.modal'),modalOrigin,done)}
function modalLeave(el,done){
const opacity=getComputedStyle(el).opacity;
for(const animation of el.getAnimations())animation.cancel();
// Hold the dimmer at zero until Vue removes the entire closing dialog.
el.animate([{opacity},{opacity:0}],{duration:380,easing:'cubic-bezier(.22,.75,.18,1)',fill:'forwards'});
collapse(el.querySelector('.modal'),modalOrigin,done)
}
function pageEnter(el,done){expand(el,pageOrigin,done);pageOrigin=null}
function pageLeave(el,done){collapse(el,null,done)}
function visit(row,event){pageOrigin=originOf(event);open(row)}
const rows=ref([]),selected=ref(null),modal=ref(false),file=ref(null),preset=ref('instrument_roformer_6s'),uploading=ref(false),uploadPercent=ref(0),error=ref(''),search=ref(''),loading=ref(false),tracks=ref([]),playing=ref(false),position=ref(0),master=ref(.65),loop=ref(false),loaded=ref(0),loadStage=ref(''),clarity=ref(false),clarityControl=ref({clarityStrength:100}),exporting=ref(''),downloadDialog=ref(null);
let context,masterNode,sources=[],buffers=new Map(),origin=0,raf,timer,revision=0,loadController;
const names={original:'원본 음원',vocals:'보컬',drums:'드럼',bass:'베이스',guitar:'기타',piano:'피아노',other:'나머지 소리',instrumental:'전체 반주'};
const colors={original:'#c7ccd9',vocals:'#af8fff',drums:'#ef9b63',bass:'#6ad6b3',guitar:'#73a9ff',piano:'#e6c66d',other:'#d090c7',instrumental:'#8da9d7'};
const filtered=computed(()=>rows.value.filter(r=>r.name.toLowerCase().includes(search.value.toLowerCase())));
const active=computed(()=>rows.value.filter(r=>['QUEUED','RUNNING'].includes(r.state)));
const completed=computed(()=>rows.value.filter(r=>r.state==='SUCCEEDED').length);
const duration=computed(()=>selected.value?.duration||0);
const stamp=s=>{s=Math.max(0,s||0);return Math.floor(s/60).toString().padStart(2,'0')+':'+Math.floor(s%60).toString().padStart(2,'0')};
const modelName=m=>({instrument_roformer_6s:'RoFormer · 6 tracks',vocal_roformer:'RoFormer · vocals',quality_6s:'Demucs · 6 tracks',quality_ft:'Demucs · fine-tuned',baseline:'Demucs · 4 tracks'}[m]||m);
const stateName=s=>({SUCCEEDED:'완료',RUNNING:'분석 중',QUEUED:'대기 중',FAILED:'실패',CANCELLED:'취소'}[s]||s);
async function request(url,options){const r=await fetch(url,options);if(!r.ok){const d=await r.json();throw Error(d.error||'요청을 처리하지 못했습니다.')}return r.json()}
async function refresh(){try{rows.value=await request('/api/analyses');if(selected.value && selected.value.state!=='SUCCEEDED'){const row=rows.value.find(r=>r.id===selected.value.id);if(row){selected.value=row;if(row.state==='SUCCEEDED')await open(row)}}}catch(e){error.value=e.message}}
function stop(){if(playing.value&&context)position.value=Math.min(duration.value,context.currentTime-origin);playing.value=false;for(const s of sources){try{s.source.stop()}catch{}}sources=[];cancelAnimationFrame(raf)}
function mix(){if(!context)return;masterNode.gain.setValueAtTime(master.value,context.currentTime);const solo=tracks.value.some(t=>t.solo);for(const s of sources){const t=tracks.value.find(t=>t.family===s.family);s.gain.gain.setTargetAtTime(t&&(!t.mute||t.solo)&&(!solo||t.solo)?t.volume:0,context.currentTime,.015);updateFilters(s.filters,clarity.value,clarityControl.value.clarityStrength,context)}}
function audioContext(){if(!context){context=new AudioContext();masterNode=context.createGain();masterNode.connect(context.destination)}return context}
async function open(row){
clarity.value=false;clarityControl.value.clarityStrength=100;
stop();loadController?.abort();revision++;const token=revision;selected.value=row;tracks.value=[];position.value=0;buffers.clear();loaded.value=0;error.value='';loading.value=false;
if(row.state!=='SUCCEEDED')return;
loadController=new AbortController();const signal=loadController.signal;loading.value=true;loadStage.value='파형과 트랙 정보를 준비하고 있습니다';
try{
const detail=await request('/api/analyses/'+row.id,{signal});if(token!==revision)return;
await settled();if(token!==revision)return;
selected.value=detail;tracks.value=[...(detail.original_url?[{family:'original',url:detail.original_url,download:'/api/analyses/'+row.id+'/download/original',waveform:[],reference:true}]:[]),...detail.tracks].map(t=>({...t,mute:t.family==='original',solo:false,volume:1,clarityStrength:100}));
for(const t of tracks.value){
loadStage.value=names[t.family]+' 트랙을 불러오고 있습니다';
const response=await fetch(t.url,{signal});if(!response.ok)throw Error('트랙을 불러오지 못했습니다.');
const buffer=await audioContext().decodeAudioData(await response.arrayBuffer());if(token!==revision)return;
buffers.set(t.family,buffer);
if(t.family==='original'){
const channels=Array.from({length:buffer.numberOfChannels},(_,i)=>buffer.getChannelData(i));const size=Math.max(1,Math.ceil(buffer.length/1200));const peaks=[];
for(let start=0;start<buffer.length;start+=size){let peak=0;for(let i=start;i<Math.min(start+size,buffer.length);i+=4)for(const channel of channels)peak=Math.max(peak,Math.abs(channel[i]));peaks.push(peak)}
t.waveform=peaks;
}
loaded.value=buffers.size;
}
}catch(e){if(token===revision&&e.name!=='AbortError')error.value=e.message}
finally{if(token===revision){await settled();if(token!==revision)return;loading.value=false;await nextTick();requestAnimationFrame(draw)}}
}
function home(event){pageOrigin=originOf(event);stop();loadController?.abort();revision++;loading.value=false;selected.value=null;buffers.clear();tracks.value=[];error.value=''}
function draw(){document.querySelectorAll('canvas[data-wave]').forEach(canvas=>{const t=tracks.value.find(t=>t.family===canvas.dataset.wave);if(!t)return;const w=Math.max(300,canvas.clientWidth),h=canvas.clientHeight,dpr=devicePixelRatio||1;canvas.width=w*dpr;canvas.height=h*dpr;const c=canvas.getContext('2d');c.scale(dpr,dpr);c.fillStyle=colors[t.family]||'#aaa';const p=t.waveform,peak=Math.max(.02,...p);for(let x=0;x<w;x+=3){const value=p[Math.floor(x/w*p.length)]||0;const height=Math.max(1,value/peak*(h-12));c.globalAlpha=.75;c.fillRect(x,(h-height)/2,1.5,height)}})}
async function toggle(){
if(playing.value){stop();return}
if(loading.value||!tracks.value.length||loaded.value!==tracks.value.length)return;
error.value='';const token=revision;
try{await context.resume();if(token!==revision)return;
if(position.value>=duration.value-.05)position.value=0;
const start=context.currentTime+.08;origin=start-position.value;
sources=tracks.value.map(t=>{const source=context.createBufferSource(),gain=context.createGain();source.buffer=buffers.get(t.family);const chain=filters(context,t.family);let tail=source;for(const f of chain){tail.connect(f.node);tail=f.node}tail.connect(gain);gain.connect(masterNode);updateFilters(chain,clarity.value,clarityControl.value.clarityStrength,context);source.start(start,position.value);return{source,gain,filters:chain,family:t.family}});
playing.value=true;mix();tick()
}catch(e){if(token===revision)error.value=e.message}
}
function toggleClarity(){if(clarity.value)clarityControl.value.clarityStrength=100;mix()}
function downloadChoice(track,event){
const snapshot=track?[track]:tracks.value.filter(t=>!t.reference);
if(!clarity.value||track?.reference){window.location.href=track?track.download:selected.value.archive_url;return}
modalOrigin=originOf(event);downloadDialog.value={id:selected.value.id,name:track?names[track.family]:'전체 트랙',tracks:snapshot.map(t=>({family:t.family,strength:clarityControl.value.clarityStrength,download:t.download})),single:!!track};
}
function downloadUrl(mode){const d=downloadDialog.value;if(!d)return '#';
if(d.single&&mode==='raw')return d.tracks[0].download;
if(d.single&&mode==='enhanced')return '/api/analyses/'+d.id+'/enhanced/'+d.tracks[0].family+'?strength='+d.tracks[0].strength;
if(!d.single&&mode==='raw')return '/api/analyses/'+d.id+'/archive';
return '/api/analyses/'+d.id+'/bundle?mode='+mode+'&settings='+encodeURIComponent(JSON.stringify(Object.fromEntries(d.tracks.map(t=>[t.family,t.strength]))));
}
let knobStart;
function knobDown(event,track){knobStart={y:event.clientY,value:track.clarityStrength};event.currentTarget.setPointerCapture(event.pointerId)}
function knobMove(event,track){if(!event.currentTarget.hasPointerCapture(event.pointerId)||!knobStart)return;track.clarityStrength=Math.max(0,Math.min(100,Math.round(knobStart.value+(knobStart.y-event.clientY)*.7)));mix()}
function knobKey(event,track){const amount={ArrowUp:1,ArrowRight:1,ArrowDown:-1,ArrowLeft:-1,PageUp:10,PageDown:-10}[event.key];if(amount!==undefined){event.preventDefault();track.clarityStrength=Math.max(0,Math.min(100,track.clarityStrength+amount));mix()}else if(event.key==='Home'||event.key==='End'){event.preventDefault();track.clarityStrength=event.key==='Home'?0:100;mix()}}
function tick(){if(!playing.value)return;position.value=Math.max(0,context.currentTime-origin);if(position.value>=duration.value){stop();position.value=0;if(loop.value)toggle();return}raf=requestAnimationFrame(tick)}
function seek(event){const was=playing.value;stop();position.value=Math.min(duration.value,Math.max(0,Number(event.target.value)));if(was)toggle()}
function seekWave(event){const rect=event.currentTarget.getBoundingClientRect();const was=playing.value;stop();position.value=(event.clientX-rect.left)/rect.width*duration.value;if(was)toggle()}
function choose(e){file.value=e.target.files?.[0]||e.dataTransfer?.files?.[0]||null}
function newAnalysis(event){modalOrigin=originOf(event);modal.value=true;file.value=null;error.value=''}
async function submit(){if(!file.value||uploading.value)return;if(!/\.(mp3|wav|flac)$/i.test(file.value.name)){error.value='MP3, WAV, FLAC 파일을 선택해 주세요.';return}uploading.value=true;uploadPercent.value=0;error.value='';try{const row=await new Promise((resolve,reject)=>{const xhr=new XMLHttpRequest();xhr.open('POST','/api/analyses?preset='+preset.value);xhr.setRequestHeader('X-Filename',encodeURIComponent(file.value.name));xhr.upload.onprogress=e=>{if(e.lengthComputable)uploadPercent.value=Math.round(e.loaded/e.total*100)};xhr.onload=()=>{try{const data=JSON.parse(xhr.responseText);xhr.status<300?resolve(data):reject(Error(data.error))}catch{reject(Error('업로드 응답을 확인할 수 없습니다.'))}};xhr.onerror=()=>reject(Error('서버에 연결하지 못했습니다.'));xhr.send(file.value)});modal.value=false;await refresh();await open(row)}catch(e){error.value=e.message}finally{uploading.value=false}}
onMounted(()=>{refresh();timer=setInterval(refresh,1800);window.addEventListener('resize',draw)});
onBeforeUnmount(()=>{loadController?.abort();revision++;stop();clearInterval(timer);window.removeEventListener('resize',draw);context?.close()});
</script>

<template>
<div class="studio" @pointerdown="press" :class="{'is-playing':playing}">
<aside class="sidebar"><a class="brand" href="#" @click.prevent="home"><span class="logo">≋</span><span>music<span class="brand-thin">analyzer</span><small>YOUR SOUND, UNLAYERED.</small></span></a><div class="workspace-label">WORKSPACE</div><button class="nav active" @click="home"><span>⌂</span>홈 & 라이브러리</button><button class="nav" @click="newAnalysis"><span>＋</span>새 분석 만들기</button><div class="side-divider"></div><div class="workspace-label">라이브러리</div><div class="side-meta"><span>완료한 분석</span><b>{{completed}}</b></div><div class="side-meta"><span>진행 중인 분석</span><b>{{active.length}}</b></div><div class="side-bottom"><span class="online-dot"></span> 로컬 스튜디오<small>음원은 이 PC에서 처리됩니다.</small></div></aside>
<main>
<header class="topbar"><div><span class="crumb">워크스페이스</span><span class="slash">/</span><span>{{selected?'트랙 스튜디오':'홈'}}</span></div><div class="top-right"><span class="status-pill"><i></i> Local engine</span><button class="button small" @click="newAnalysis">＋ 새 분석</button></div></header>
<div v-if="error&&!modal" role="alert" class="error">{{error}}<button @click="error=''">닫기</button></div>
<Transition :css="false" mode="out-in" @enter="pageEnter" @leave="pageLeave" @after-enter="draw"><section v-if="!selected" key="home" class="home">
<div class="page-heading"><div class="eyebrow">A SPACE FOR YOUR SOUND</div><h1>음악을, 한 트랙씩.</h1><p>음원을 선택하고 각 악기의 소리를 만나보세요.</p></div>
<div class="hero"><div class="hero-copy"><span class="tiny-label">CREATE A NEW SESSION</span><h2>하나의 곡에서<br>여러 개의 가능성으로.</h2><p>보컬부터 기타, 드럼, 베이스까지.<br>분리하고, 함께 듣고, 필요한 트랙을 다운로드하세요.</p><button class="button white" @click="newAnalysis">＋ 새 분석 만들기 <span>↗</span></button><div class="hero-tags">MP3 · WAV · FLAC <span>최대 15분</span></div></div><div class="hero-art" aria-hidden="true"><div v-for="(color,i) in ['#c6b2ff','#72d5b5','#edaf72','#88b8ff','#e2c77f']" :key="color" class="art-track" :style="{'--tint':color,transform:'translateX('+(i%2?25:0)+'px)'}"><span class="art-dot"></span><div class="art-wave"><i v-for="n in 58" :key="n" :style="{height:(8+Math.abs(Math.sin(n*2.7+i)*Math.cos(n*.2+i))*35)+'px'}"></i></div></div><div class="art-playhead"></div><div class="art-badge">6 independent tracks <span>◉</span></div></div></div>
<div class="library-heading"><div><h2>내 분석 라이브러리 <span>{{rows.length}}</span></h2><p>이전에 분석한 곡을 이어서 확인하세요.</p></div><label class="search"><span>⌕</span><input v-model="search" placeholder="곡 이름 검색" aria-label="곡 이름 검색"></label></div>
<div class="library"><div class="table-header"><span>곡 이름</span><span>모델</span><span>길이</span><span>상태</span><span></span></div><button v-for="(row,i) in filtered" :key="row.id" class="library-row" @click="visit(row,$event)"><div class="song-cell"><div class="song-icon" :style="{'--accent':['#b39bfa','#74c9b1','#8ab5e5','#dda778'][i%4]}">≋</div><div><strong>{{row.name}}</strong><small>{{row.track_count}} tracks <span>·</span> {{typeof row.created==='string'?row.created.slice(0,10):'이전 분석'}}</small></div></div><span class="model-label">{{modelName(row.model)}}</span><span class="duration">{{stamp(row.duration)}}</span><span class="badge" :class="row.state">{{stateName(row.state)}}<span v-if="row.state==='RUNNING'"> · {{row.progress}}%</span></span><span class="arrow">↗</span></button><div v-if="!filtered.length" class="empty">{{search?'검색 결과가 없습니다.':'아직 분석한 곡이 없습니다. 첫 음원을 추가해 보세요.'}}</div></div><footer class="home-footer">CREATED FOR LISTENING. BUILT FOR EXPLORING.<span>Music Analyzer / Local workspace</span></footer>
</section>
<section v-else :key="selected.id" class="session">
<button class="back" @click="home">← 라이브러리로 돌아가기</button>
<div class="session-heading"><div><div class="eyebrow">TRACK SESSION</div><h1>{{selected.name}}</h1><p><template v-if="selected.vocal_source==='roformer'">보컬 RoFormer <span>+</span> 악기 </template>{{modelName(selected.model)}} <span>·</span> {{stamp(duration)}} <span>·</span> {{selected.track_count}} stems<template v-if="tracks.some(t=>t.reference)"> <span>+</span> 원본</template></p></div><div v-if="selected.archive_url" class="session-actions"><label class="clarity-toggle"><span>선명도</span><input v-model="clarity" type="checkbox" role="switch" aria-label="선명도 후처리" @change="toggleClarity"><i></i></label><div class="clarity-knob-control" :class="{disabled:!clarity}"><div class="clarity-knob" role="slider" :tabindex="clarity?0:-1" :aria-disabled="!clarity" :aria-label="'전체 선명도 강도'" aria-valuemin="0" aria-valuemax="100" :aria-valuenow="clarityControl.clarityStrength" :aria-valuetext="clarityControl.clarityStrength+'%'" :style="{'--knob-angle':(clarityControl.clarityStrength*2.7-135)+'deg','--knob-fill':clarityControl.clarityStrength*2.7+'deg'}" @pointerdown.prevent="clarity&&knobDown($event,clarityControl)" @pointermove="clarity&&knobMove($event,clarityControl)" @keydown="clarity&&knobKey($event,clarityControl)"><i></i></div><span>선명도 <b>{{clarityControl.clarityStrength}}%</b><small v-if="!clarity" class="knob-off-label">OFF</small></span></div><button class="button" @click="downloadChoice(null,$event)">↓ 전체 트랙 다운로드</button></div></div>
<div v-if="selected.state!=='SUCCEEDED'" class="processing"><div v-if="selected.state!=='FAILED'" class="spinner"></div><div v-else class="failed-symbol">!</div><span class="tiny-label">ANALYSIS SESSION</span><h2>{{selected.stage}}</h2><p v-if="selected.state!=='FAILED'">조금만 기다려 주세요. 각 트랙의 소리를 분리하고 있습니다.</p><p v-else>{{selected.error}}</p><div class="progress-line"><i :style="{width:selected.progress+'%'}"></i></div><div class="progress-caption"><span>{{selected.completed_chunks||0}} / {{selected.total_chunks||'—'}} 구간</span><b>{{selected.progress}}%</b></div><div class="stage-steps"><span :class="{done:selected.progress>5}">01 보컬 분리</span><span :class="{done:selected.progress>50}">02 악기 분리</span><span>03 결과 준비</span></div></div>
<template v-else>
<div v-if="loading" class="track-loading" role="status" aria-live="polite" aria-busy="true">
<div class="spinner"></div><h2>트랙을 준비하고 있습니다</h2><p>{{loadStage}}</p>
<div class="progress-line"><i :style="{width:(tracks.length?loaded/tracks.length*100:0)+'%'}"></i></div>
<div class="progress-caption"><span>{{loaded}} / {{tracks.length||selected.track_count||'—'}} 트랙</span><b>{{tracks.length?Math.round(loaded/tracks.length*100):0}}%</b></div>
</div>
<div v-else-if="tracks.length&&loaded!==tracks.length" class="track-loading"><h2>트랙을 불러오지 못했습니다</h2><button class="button" @click="open(selected)">다시 불러오기</button></div>
<template v-else>
<div class="transport"><div class="play-controls"><button class="reset" aria-label="처음으로" @click="stop();position=0">↤</button><button class="play" :disabled="loading" @click="toggle" :aria-label="playing?'일시정지':'재생'">{{loading?'◌':playing?'Ⅱ':'▶'}}</button><button class="reset" :class="{enabled:loop}" aria-label="전체 곡 반복" @click="loop=!loop">↻</button><div class="time"><strong>{{stamp(position)}}</strong><span>/ {{stamp(duration)}}</span></div></div><div class="transport-right"><span v-if="loading" class="loading-text">트랙 불러오는 중 {{loaded}} / {{tracks.length}}</span><span class="rate">44.1 kHz <span>STEREO</span></span><label class="master">마스터<input v-model.number="master" type="range" min="0" max="1" step=".01" @input="mix" aria-label="마스터 음량"></label></div></div>
<div class="daw" :class="{'daw-playing':playing,'has-clarity':clarity}">
<div class="daw-ruler"><span>TRACKS <b>{{tracks.length}}</b></span><div><i v-for="n in 9" :key="n">{{stamp((n-1)/8*duration)}}</i></div><span></span></div>
<div v-for="(track,i) in tracks" :key="track.family" class="track-row" :style="{'--track':colors[track.family],'--index':i}" :class="{muted:track.mute,solo:track.solo}">
<div class="track-info"><div class="track-title"><span class="track-number">{{String(i+1).padStart(2,'0')}}</span><b>{{names[track.family]||track.family}}</b><span class="track-format">{{track.reference?'REF':'WAV'}}</span></div><div class="track-settings"><button :class="{selected:track.mute}" @click="track.mute=!track.mute;mix()" :aria-label="names[track.family]+' 음소거'" :aria-pressed="track.mute">M</button><button :class="{selected:track.solo}" @click="track.solo=!track.solo;mix()" :aria-label="names[track.family]+' 솔로'" :aria-pressed="track.solo">S</button><input v-model.number="track.volume" type="range" min="0" max="1.5" step=".01" @input="mix" :aria-label="names[track.family]+' 음량'"><span>{{Math.round(track.volume*100)}}%</span></div></div>
<div class="waveform" @click="seekWave"><canvas :data-wave="track.family"></canvas><div class="playhead" :style="{left:(position/duration*100)+'%'}"></div></div><button class="track-download" @click="downloadChoice(track,$event)" :aria-label="names[track.family]+' WAV 다운로드'">↓</button></div>
<div v-if="loading&&!tracks.length" class="empty">파형을 준비하고 있습니다…</div>
</div><input class="timeline" type="range" :value="position" min="0" :max="duration" step=".1" @input="seek" aria-label="재생 위치"><div class="session-foot"><span>원본은 기본 음소거입니다. 원본의 S 버튼으로 분리 결과와 비교하세요.</span><span>다운로드는 원본 FLOAT WAV · 음량 조절은 재생에만 적용</span></div>
</template></template></section></Transition>
</main>
<Transition :css="false" @enter="modalEnter" @leave="modalLeave"><div v-if="modal" class="modal-backdrop" @click.self="!uploading&&(modal=false)" @keydown.esc="!uploading&&(modal=false)">
<form class="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title" @submit.prevent="submit"><div class="modal-top"><span class="tiny-label">NEW ANALYSIS</span><button type="button" class="close" @click="modal=false" :disabled="uploading" aria-label="닫기">×</button></div><h2 id="modal-title">새로운 소리를 발견하세요.</h2><p>원본 음원을 선택하면 트랙 분리가 시작됩니다.</p><label class="dropzone" @dragover.prevent @drop.prevent="choose"><input type="file" accept=".mp3,.wav,.flac" @change="choose" :disabled="uploading" aria-label="음원 파일 선택"><span class="upload-symbol">↥</span><strong>{{file?file.name:'음원을 드래그하거나 클릭해 선택'}}</strong><small>{{file?(file.size/1024/1024).toFixed(1)+' MB':'MP3, WAV, FLAC · 최대 1GB / 15분'}}</small></label><label class="field-label">악기 분리 모델<select v-model="preset" :disabled="uploading"><option value="instrument_roformer_6s">BS-RoFormer · 최신 악기 후보</option><option value="quality_6s">Demucs · 기존 6트랙 모델</option></select></label><div class="modal-note"><span>◈</span><p>보컬은 확정한 RoFormer로 먼저 분리합니다.<br>파일은 외부로 전송하지 않고 이 PC에서 분석합니다.</p></div><div v-if="error" role="alert" class="error">{{error}}</div><div v-if="uploading" class="upload-state"><span>음원 업로드 중</span><b>{{uploadPercent}}%</b><div class="progress-line"><i :style="{width:uploadPercent+'%'}"></i></div></div><button class="button full" type="submit" :disabled="!file||uploading">{{uploading?'음원 업로드 중…':'분석 시작하기'}} <span>→</span></button></form>
</div></Transition>
<Transition :css="false" @enter="modalEnter" @leave="modalLeave"><div v-if="downloadDialog" class="modal-backdrop" @click.self="downloadDialog=null" @keydown.esc="downloadDialog=null"><div class="modal download-modal" role="dialog" aria-modal="true" aria-labelledby="download-title"><div class="modal-top"><span class="tiny-label">DOWNLOAD TRACKS</span><button class="close" aria-label="다운로드 창 닫기" @click="downloadDialog=null">×</button></div><h2 id="download-title">어떤 파일로 받을까요?</h2><p>{{downloadDialog.name}} · 개선음은 현재 노브 값을 적용합니다.</p><div class="download-values"><span v-for="t in downloadDialog.tracks" :key="t.family">{{names[t.family]}} {{t.strength}}%</span></div><a class="download-option" :href="downloadUrl('enhanced')">선명도 처리된 파일 <small>현재 설정을 적용한 WAV{{downloadDialog.single?'':' ZIP'}}</small><b>↗</b></a><a class="download-option" :href="downloadUrl('raw')">그냥 받기 <small>후처리 전 분리 원음</small><b>↗</b></a><a class="download-option" :href="downloadUrl('both')">둘 다 받기 <small>원음과 개선음을 폴더별로 담은 ZIP</small><b>↗</b></a></div></div></Transition>
</div>
</template>