<script setup>
import {ref,computed,onMounted,onBeforeUnmount,nextTick} from 'vue';
import {Drum} from '@lucide/vue';
import {mdiBellRing,mdiMicrophone,mdiAccountGroup,mdiPiano,mdiTune,mdiViolin,mdiTrumpet,mdiGuitarAcoustic,mdiGuitarElectric,mdiWaveform,mdiDisc,mdiMusicNote} from '@mdi/js';
import {filters,updateFilters} from './clarity';
import {estimateAnalysis,formatEstimate} from './analysisEstimate';
import {trackLevels} from './trackGroups';
import {BufferedPlayer} from './bufferPlayer';
import {originOf,expand,collapse,press,settled} from './motion';
const props=defineProps({user:{type:Object,default:null},accountBusy:{type:Boolean,default:false}});
const emit=defineEmits(['logout','login']);
let modalOrigin,pageOrigin;
function modalEnter(el,done){el.animate([{opacity:0},{opacity:1}],{duration:420,easing:'cubic-bezier(.22,.75,.18,1)'});expand(el.querySelector('.modal'),modalOrigin,done)}
function modalLeave(el,done){
const opacity=getComputedStyle(el).opacity;
for(const animation of el.getAnimations())animation.cancel();
// Hold the dimmer at zero until Vue removes the entire closing dialog.
el.animate([{opacity},{opacity:0}],{duration:380,easing:'cubic-bezier(.22,.75,.18,1)',fill:'forwards'});
collapse(el.querySelector('.modal'),modalOrigin,done)
}
function fade(el,from,to,done){let over=false;const end=()=>{if(!over){over=true;done()}};el.animate([{opacity:from},{opacity:to}],{duration:260,easing:'ease'}).onfinish=end;setTimeout(end,400)}
function pageEnter(el,done){fade(el,0,1,done)}
function pageLeave(el,done){fade(el,1,0,done)}
function visit(row,event){pageOrigin=originOf(event);open(row)}
const page=ref('home'),rows=ref([]),selected=ref(null),modal=ref(false),file=ref(null),preset=ref(''),uploadStep=ref(1),uploading=ref(false),uploadPercent=ref(0),error=ref(''),search=ref(''),loading=ref(false),tracks=ref([]),playing=ref(false),position=ref(0),master=ref(1),loop=ref(false),loaded=ref(0),loadStage=ref(''),clarity=ref(false),clarityControl=ref({clarityStrength:100}),exporting=ref(''),downloadDialog=ref(null),logoutDialog=ref(false);
let bufferedPlayer=null,windowed=false,startRevision=0,disposed=false;
const starting=ref(false);
const fileDuration=ref(null),readingFile=ref(false);
let metadataAudio=null,metadataUrl=null,metadataTimer;
function clearMetadata(){clearTimeout(metadataTimer);if(metadataAudio){metadataAudio.onloadedmetadata=null;metadataAudio.onerror=null;metadataAudio.removeAttribute('src');metadataAudio.load();metadataAudio=null}if(metadataUrl){URL.revokeObjectURL(metadataUrl);metadataUrl=null}}
function versionEstimate(model){return estimateAnalysis(fileDuration.value,model,rows.value)}
let context,masterNode,sources=[],buffers=new Map(),origin=0,raf,timer,revision=0,loadController;
const expandedGroups=ref({});
const trackOrder=['lead','vocals','backing','piano','synth','strings','brass','acoustic_guitar','guitar','guitar_residual','bass','drums','percussion','other','instrumental','original'];
const visibleTracks=computed(()=>[...tracks.value].sort((a,b)=>(trackOrder.indexOf(a.family)<0?99:trackOrder.indexOf(a.family))-(trackOrder.indexOf(b.family)<0?99:trackOrder.indexOf(b.family))));
function trackTitle(t){return ['other','guitar_residual'].includes(t.family)?names[t.family]:(t.display_name||names[t.family]||t.family)}
const trackIcons={lead:mdiMicrophone,vocals:mdiMicrophone,backing:mdiAccountGroup,piano:mdiPiano,synth:mdiTune,strings:mdiViolin,brass:mdiTrumpet,acoustic_guitar:mdiGuitarAcoustic,guitar:mdiGuitarElectric,bass:mdiGuitarElectric,percussion:mdiBellRing,other:mdiWaveform,instrumental:mdiMusicNote,original:mdiDisc};
const names={lead:'보컬',backing:'코러스',original:'원본 음원',vocals:'보컬',drums:'드럼',bass:'베이스',guitar:'일렉기타',piano:'피아노',synth:'신디사이저',strings:'스트링',brass:'브라스',acoustic_guitar:'어쿠스틱기타',guitar_residual:'기타 보조',percussion:'기타 타악기',other:'추가 반주',instrumental:'전체 반주'};
const colors={brass:'#e6aa5b',strings:'#93c5c0',acoustic_guitar:'#cda76c',synth:'#d090c7',synth_pad:'#d090c7',other_residual:'#8da9d7',lead_guitar:'#73a9ff',guitar_residual:'#6ad6b3',lead:'#af8fff',backing:'#e4a6d3',original:'#c7ccd9',vocals:'#af8fff',drums:'#ef9b63',bass:'#6ad6b3',guitar:'#73a9ff',piano:'#e6c66d',other:'#d090c7',instrumental:'#8da9d7',percussion:'#e8d27f'};
const compare=[{id:'basic_2',title:'2트랙',lead:'보컬과 반주',tracks:[['보컬','vocals'],['전체 반주','instrumental']],text:'가장 빨리 끝나요. 코러스는 보컬에 같이 들어 있어요.',fit:'노래방 MR · 보컬 연습 · 커버 작업'},{id:'basic_6',title:'6트랙',lead:'밴드 구성 분리',tracks:[['보컬','vocals'],['기타','guitar'],['베이스','bass'],['드럼','drums'],['피아노','piano'],['추가 반주','other']],text:'기타는 통기타·일렉 구분 없이 하나로 나오고, 신디·스트링·브라스는 추가 반주에 들어 있어요.',fit:'밴드 연습 · 파트 카피 · 리믹스 기초'},{id:'final_11',title:'13트랙',lead:'풀밴드와 오케스트라 까지',tracks:[['보컬','lead'],['코러스','backing'],['피아노','piano'],['신디사이저','synth'],['스트링','strings'],['브라스','brass'],['통기타','acoustic_guitar'],['일렉기타','guitar'],['베이스','bass'],['드럼','drums'],['추가 반주','other'],['기타 보조','guitar_residual'],['기타 타악기','percussion']],text:'보컬·코러스부터 신디, 스트링, 브라스, 기타까지 악기별로 따로 나와요. 종소리·팀파니는 기타 타악기에 담겨요.',fit:'편곡 분석 · 악기별 학습 · 정밀 믹싱'}];
const features=[{icon:'≋',title:'13트랙 정밀 분리',text:'보컬부터 드럼, 베이스, 기타, 건반까지 파트별로 나뉘어요.'},{icon:'◎',title:'원곡 문맥 보정',text:'원곡을 함께 살펴서, 엉뚱한 트랙에 섞인 소리를 제자리로 옮겨요.'},{icon:'▶',title:'트랙 스튜디오',text:'트랙마다 음소거, 솔로, 볼륨을 조절하며 바로 들어볼 수 있어요.'},{icon:'↓',title:'개별·전체 다운로드',text:'트랙 하나만, 또는 전체를 한 번에 받을 수 있어요.'},{icon:'⌂',title:'내 PC에서 처리',text:'음원은 이 PC의 로컬 엔진에서 처리되며 계정별 라이브러리에 보관됩니다.'},{icon:'✦',title:'선명도 후처리',text:'분리 후 남는 잡음을 줄이는 선명도 조절을 한 번에 적용합니다.'}];
const chipTracks=['보컬','코러스','피아노','신디사이저','스트링','브라스','어쿠스틱기타','일렉기타','베이스','드럼','추가 반주','기타 보조','기타 타악기'];
const howTo=[['음원 올리기','새 분석에서 MP3·WAV·FLAC 파일을 올려요.'],['구성 고르기','2·6·13트랙 중에 원하는 걸 골라요.'],['듣고 받기','트랙을 섞어 들어 보고 필요한 것만 받아요.']];
const studioFeatures=[['M','트랙별 음소거','듣기 싫은 트랙만 끌 수 있어요.','is-m'],['S','트랙별 솔로','원하는 트랙 소리만 따로 들어요.','is-s'],['◖━','볼륨 조절','트랙마다 소리 크기를 맞춰요.','is-v'],['↺','전체 해제','켜진 음소거·솔로를 한 번에 풀고, 다시 누르면 이전 상태로 돌아가요.','is-r'],['▶','재생과 이동','스페이스바로 재생·정지, 재생바를 눌러 원하는 구간으로 가요.','is-p'],['↓','개별 다운로드','트랙 하나만, 또는 전체를 한 번에 받아요.','is-d']];
const filtered=computed(()=>rows.value.filter(r=>r.name.toLowerCase().includes(search.value.toLowerCase())));
const active=computed(()=>rows.value.filter(r=>['QUEUED','RUNNING'].includes(r.state)));
const completed=computed(()=>rows.value.filter(r=>r.state==='SUCCEEDED').length);
const duration=computed(()=>selected.value?.duration||0);
const versions=[
{id:'basic_2',title:'2트랙',description:'보컬 + 전체 반주',note:'메인보컬과 코러스를 함께 유지합니다.',steps:[['음원 변환',5,'원본을 44.1kHz 스테레오 WAV로 준비합니다.'],['보컬·반주 분리',32,'원곡에서 보컬과 전체 반주를 추출합니다.'],['최종 결과 저장',100,'길이와 원곡 대비 합계 보존을 검증하고 저장합니다.']]},
{id:'basic_6',title:'6트랙',description:'보컬 · 기타 · 베이스 · 드럼 · 피아노 · 추가 반주',note:'기타는 통기타와 일렉을 구분하지 않습니다.\n신디·스트링·브라스는 별도 추출하지 않습니다.',steps:[['음원 변환',5,'원본을 44.1kHz 스테레오 WAV로 준비합니다.'],['보컬·반주 분리',32,'메인보컬과 코러스를 함께 추출합니다.'],['피아노·기타·베이스·드럼 추출',84,'분리된 반주에서 네 악기를 추출합니다.'],['반주 구성 정리',97,'반주에서 네 악기를 뺀 잔여 신호를 만듭니다.'],['최종 결과 저장',100,'길이와 악기·추가 반주의 반주 합계 보존을 검증합니다.']]},
{id:'final_11',title:'13트랙',description:'보컬 · 코러스 · 피아노 · 신디 · 스트링 · 브라스 · 통기타 · 일렉기타 · 베이스 · 드럼 · 추가 반주 · 기타 보조 · 기타 타악기',note:'원곡의 악기 근거로 보컬에 섞인 반주를 보완하고, 종소리·팀파니 등은 기타 타악기로 제공합니다.',steps:[['음원 변환',5,'44.1kHz 스테레오 WAV로 준비합니다.'],['보컬·반주 분리',32,'원곡에서 보컬과 반주를 추출합니다.'],['원곡 악기 근거 확인',40,'스트링·브라스·신디와 기타 타악기를 확인합니다.'],['보컬·코러스 분리',50,'보컬을 메인보컬과 코러스로 나눕니다.'],['피아노·기타·베이스·드럼 추출',70,'분리된 반주에서 네 악기를 추출합니다.'],['추가 악기 분리 준비',70,'반주에서 네 악기를 뺍니다.'],['어쿠스틱·일렉기타 분리',77,'기타를 다시 분리하고 기타 보조를 별도로 보관합니다.'],['신디·스트링·브라스 추출',84,'분리된 추가 반주에서 세 악기를 추출합니다.'],['반주 구성 정리',85,'분리된 추가 반주에서 세 악기를 뺍니다.'],['피아노 내 심벌 보완',95,'피아노의 음정을 보호하면서 심벌 혼입을 드럼으로 옮깁니다.'],['기타 타악기 분류',96,'원곡 근거를 확인해 드럼과 남은 반주에서 종소리·팀파니 등을 다시 확인해 분류합니다.'],['최종 반주 정리',98,'분류한 악기의 합계를 검증하고 남은 반주를 보관합니다.'],['최종 결과 저장',100,'13트랙을 검증하고 저장합니다.']]}

];
const chosenVersion=computed(()=>versions.find(v=>v.id===preset.value));
const analysisSteps=computed(()=>versions.find(v=>v.id===selected.value?.model)?.steps||[['음원 변환',5],['보컬·반주 분리',32],['악기 추출',66],['보컬·코러스 분리',84],['반주 구성 정리',85],['신디 보완',91],['스트링 보완',97],['최종 결과 저장',100]]);

const mixable=computed(()=>tracks.value.filter(t=>t.family!=='original'));
const allMuted=computed(()=>mixable.value.length>0&&mixable.value.every(t=>t.mute)),anyMuted=computed(()=>mixable.value.some(t=>t.mute));
const allSolo=computed(()=>mixable.value.length>0&&mixable.value.every(t=>t.solo)),anySolo=computed(()=>mixable.value.some(t=>t.solo));
// Any engaged track means the press releases every track and remembers them; the next press restores that set (or engages all if none was remembered). Original stays a reference.
let masterMemory={mute:[],solo:[]};
function masterToggle(key,any){
if(any){masterMemory[key]=mixable.value.filter(t=>t[key]).map(t=>t.family);for(const t of mixable.value)t[key]=false}
else{const saved=mixable.value.filter(t=>masterMemory[key].includes(t.family));for(const t of mixable.value)t[key]=saved.length?saved.includes(t):true}
mix()}
let resetFrame;
function resetVolumes(event){
const btn=event?.currentTarget;btn?.animate([{transform:'rotate(0)'},{transform:'rotate(-360deg)'}],{duration:600,easing:'cubic-bezier(.22,.75,.18,1)'});
cancelAnimationFrame(resetFrame);
const from=tracks.value.map(t=>t.volume),m0=master.value,start=performance.now(),ms=600;
const step=now=>{const k=Math.min(1,(now-start)/ms),e=1-Math.pow(1-k,3);
master.value=m0+(1-m0)*e;tracks.value.forEach((t,i)=>{if(from[i]!==undefined)t.volume=from[i]+(1-from[i])*e});mix();
if(k<1)resetFrame=requestAnimationFrame(step)};
resetFrame=requestAnimationFrame(step)}
const rulerTicks=computed(()=>{const d=duration.value;if(!d)return[];const step=[1,2,5,10,15,20,30,60,120,300].find(n=>d/n<=12)||600;const out=[];for(let t=0;t<d;t+=step)out.push({t,left:t/d*100});return out});
const stamp=s=>{s=Math.max(0,s||0);return Math.floor(s/60).toString().padStart(2,'0')+':'+Math.floor(s%60).toString().padStart(2,'0')};
const modelName=(m,v)=>m==='final_11'&&v&&!['staged-context-percussion-v11','staged-context-percussion-v12','staged-context-strings-v13','staged-context-backing-v14','staged-context-families-v15','staged-context-pads-v16'].includes(v)?'12트랙 분리':({basic_2:'2트랙 분리',basic_6:'6트랙 분리',final_11:'13트랙 분리',final_10:'악기별 분리',clapsep:'CLAPSep · 패드 비교',audiosep_base:'AudioSep · 목표 소리 실험',bs_karaoke:'BS-RoFormer · 리드/코러스',karaoke_roformer:'RoFormer · 리드/코러스',instrument_roformer_6s:'RoFormer · 6 tracks',vocal_roformer:'RoFormer · vocals',quality_6s:'Demucs · 6 tracks',quality_ft:'Demucs · fine-tuned',baseline:'Demucs · 4 tracks'}[m]||m);
const stateName=s=>({SUCCEEDED:'완료',RUNNING:'분석 중',QUEUED:'대기 중',FAILED:'실패',CANCELLED:'취소'}[s]||s);
async function request(url,options){const r=await fetch(url,{...options,headers:{...options?.headers,'X-Requested-With':'MusicAnalyzer'}});if(r.status===401)window.dispatchEvent(new Event('music-session-expired'));if(!r.ok){const d=await r.json();throw Error(d.error||'요청을 처리하지 못했습니다.')}return r.json()}
async function refresh(){if(!props.user||disposed)return;try{const result=await request('/api/analyses');if(disposed)return;rows.value=result;if(selected.value && selected.value.state!=='SUCCEEDED'){const row=rows.value.find(r=>r.id===selected.value.id);if(row){selected.value=row;if(row.state==='SUCCEEDED')await open(row)}}}catch(e){error.value=e.message}}
function stop(){startRevision++;starting.value=false;if(playing.value&&context)position.value=Math.min(duration.value,Math.max(0,context.currentTime-origin));playing.value=false;bufferedPlayer?.stop();for(const s of sources){try{s.source.stop()}catch{}s.source.disconnect();s.gain.disconnect();for(const f of s.filters)f.node.disconnect()}sources=[];cancelAnimationFrame(raf)}
function clearMedia(){bufferedPlayer?.dispose();bufferedPlayer=null}
function createSource(t,buffer){const source=context.createBufferSource(),gain=context.createGain();source.buffer=buffer;const chain=filters(context,t.family);let tail=source;for(const f of chain){tail.connect(f.node);tail=f.node}tail.connect(gain);gain.connect(masterNode);return{source,gain,filters:chain,family:t.family}}
function mix(){if(!context)return;masterNode.gain.setValueAtTime(master.value,context.currentTime);const levels=trackLevels(tracks.value,expandedGroups.value);for(const s of sources){s.gain.gain.setTargetAtTime(levels.get(s.family)||0,context.currentTime,.015);updateFilters(s.filters,clarity.value,clarityControl.value.clarityStrength,context)}}
function audioContext(){if(!context){context=new AudioContext();masterNode=context.createGain();masterNode.connect(context.destination)}return context}
async function open(row){
if(disposed)return;
clarity.value=false;clarityControl.value.clarityStrength=100;expandedGroups.value={};
masterMemory={mute:[],solo:[]};stop();clearMedia();loadController?.abort();revision++;const token=revision;selected.value=row;page.value='library';tracks.value=[];position.value=0;buffers.clear();loaded.value=0;error.value='';loading.value=false;
windowed=(row.duration||0)>120;
if(row.state!=='SUCCEEDED')return;
loadController=new AbortController();const signal=loadController.signal;loading.value=true;loadStage.value='파형과 트랙 정보를 준비하고 있습니다';
try{
const detail=await request('/api/analyses/'+row.id,{signal});if(token!==revision)return;
await settled();if(token!==revision)return;
selected.value=detail;tracks.value=[...(detail.original_url?[{family:'original',url:detail.original_url,download:'/api/analyses/'+row.id+'/download/original',waveform:[],reference:true}]:[]),...detail.tracks].map(t=>({...t,mute:detail.kind==='part_comparison'||t.family==='original',solo:false,volume:1,clarityStrength:100}));
if(windowed){
const ctx=audioContext();
bufferedPlayer=new BufferedPlayer({context:ctx,tracks:tracks.value,duration:detail.duration,
fetchWindow:async(t,index,signal)=>{const url=t.url+'?start_frame='+index*1323000+'&num_frames=1323000';const response=await fetch(url,{signal});if(!response.ok)throw Error((names[t.family]||t.family)+' 트랙을 불러오지 못했습니다.');return ctx.decodeAudioData(await response.arrayBuffer())},
createChain:createSource,onSources:list=>{sources=list;mix()},
onError:e=>{stop();error.value=e.message},
onProgress:(index,count,t)=>{if(token===revision&&index===0&&loading.value){loaded.value=count;loadStage.value=(names[t.family]||t.family)+' 트랙을 준비하고 있습니다'}}});
const initialPlayer=bufferedPlayer;await initialPlayer.prepare();if(token!==revision)return;
const originalTrack=tracks.value.find(t=>t.reference);if(originalTrack)originalTrack.waveform=detail.original_waveform||[];
// Warm the next window before playback without keeping the entire song in memory.
if(detail.duration>30)initialPlayer.window(1).catch(()=>{});
}else for(const t of tracks.value){
loadStage.value=(names[t.family]||t.family)+' 트랙을 불러오고 있습니다';
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
function go(target,event){page.value=target;home(event)}
function home(event){pageOrigin=originOf(event);stop();loadController?.abort();revision++;loading.value=false;selected.value=null;clearMedia();buffers.clear();tracks.value=[];error.value=''}
function draw(){document.querySelectorAll('canvas[data-wave]').forEach(canvas=>{const t=tracks.value.find(t=>t.family===canvas.dataset.wave);if(!t)return;const w=Math.max(300,canvas.clientWidth),h=canvas.clientHeight,dpr=devicePixelRatio||1;canvas.width=w*dpr;canvas.height=h*dpr;const c=canvas.getContext('2d');c.scale(dpr,dpr);c.fillStyle=colors[t.family]||'#aaa';const p=t.waveform,peak=Math.max(.02,...p);for(let x=0;x<w;x+=3){const value=p[Math.floor(x/w*p.length)]||0;const height=Math.max(1,value/peak*(h-12));c.globalAlpha=.75;c.fillRect(x,(h-height)/2,1.5,height)}})}
async function toggle(){
if(playing.value||starting.value){stop();return}
if(loading.value||!tracks.value.length||loaded.value!==tracks.value.length)return;
error.value='';const token=revision,ticket=++startRevision;starting.value=true;
try{
if(position.value>=duration.value-.05)position.value=0;
if(windowed){const player=bufferedPlayer;const started=await player.start(position.value);if(token!==revision||ticket!==startRevision||!started)return;origin=player.origin}
else{await context.resume();if(token!==revision||ticket!==startRevision)return;
const start=context.currentTime+.08;origin=start-position.value;
sources=tracks.value.map(t=>{const item=createSource(t,buffers.get(t.family));item.source.start(start,position.value);return item});mix()}
playing.value=true;tick();
}catch(e){if(token===revision&&ticket===startRevision&&e.name!=='AbortError'){stop();error.value=e.message}}
finally{if(ticket===startRevision)starting.value=false}
}
function toggleClarity(){if(clarity.value)clarityControl.value.clarityStrength=100;mix()}
function downloadChoice(track,event){
const snapshot=track?[track]:tracks.value.filter(t=>!t.reference);
if(!clarity.value||track?.reference){window.location.href=track?track.download:selected.value.archive_url;return}
modalOrigin=originOf(event);downloadDialog.value={id:selected.value.id,name:track?trackTitle(track):'전체 트랙',tracks:snapshot.map(t=>({family:t.family,strength:clarityControl.value.clarityStrength,download:t.download})),single:!!track};
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
function seek(event){const was=playing.value||starting.value;stop();position.value=Math.min(duration.value,Math.max(0,Number(event.target.value)));if(was)toggle()}
function seekWave(event){const rect=event.currentTarget.getBoundingClientRect();const was=playing.value||starting.value;stop();position.value=(event.clientX-rect.left)/rect.width*duration.value;if(was)toggle()}
function choose(e){
if(uploading.value)return;
clearMetadata();fileDuration.value=null;readingFile.value=false;error.value='';
file.value=e.target.files?.[0]||e.dataTransfer?.files?.[0]||null;
if(!file.value)return;
if(!/\.(mp3|wav|flac)$/i.test(file.value.name)){error.value='MP3, WAV, FLAC 파일을 선택해 주세요.';file.value=null;return}
if(file.value.size===0||file.value.size>1024**3){error.value='파일은 1GB 이하의 음원을 선택해 주세요.';file.value=null;return}
readingFile.value=true;const audio=new Audio();metadataAudio=audio;metadataUrl=URL.createObjectURL(file.value);audio.preload='metadata';
audio.onloadedmetadata=()=>{const length=audio.duration;readingFile.value=false;if(Number.isFinite(length)&&length>0){fileDuration.value=length;if(length>900){error.value='15분 이하의 음원을 선택해 주세요.';file.value=null;fileDuration.value=null}}clearMetadata()};
audio.onerror=()=>{readingFile.value=false;clearMetadata()};
metadataTimer=setTimeout(()=>{readingFile.value=false;clearMetadata()},10000);audio.src=metadataUrl;
}
async function splitVocals(){if(loading.value)return;error.value='';try{const row=await request('/api/analyses/'+selected.value.id+'/vocal-detail',{method:'POST'});await refresh();await open(row)}catch(e){error.value=e.message}}
function newAnalysis(event){if(!props.user){emit('login',event);return}modalOrigin=originOf(event);modal.value=true;uploadStep.value=1;preset.value='';file.value=null;fileDuration.value=null;readingFile.value=false;clearMetadata();error.value=''}
async function submit(){if(uploadStep.value===1){if(file.value&&!readingFile.value)uploadStep.value=2;return}if(!chosenVersion.value||!file.value||uploading.value)return;if(!/\.(mp3|wav|flac)$/i.test(file.value.name)){error.value='MP3, WAV, FLAC 파일을 선택해 주세요.';return}uploading.value=true;uploadPercent.value=0;error.value='';try{const row=await new Promise((resolve,reject)=>{const xhr=new XMLHttpRequest();xhr.open('POST','/api/analyses?preset='+preset.value);xhr.setRequestHeader('X-Requested-With','MusicAnalyzer');xhr.setRequestHeader('X-Filename',encodeURIComponent(file.value.name));xhr.upload.onprogress=e=>{if(e.lengthComputable)uploadPercent.value=Math.round(e.loaded/e.total*100)};xhr.onload=()=>{if(xhr.status===401)window.dispatchEvent(new Event('music-session-expired'));try{const data=JSON.parse(xhr.responseText);xhr.status<300?resolve(data):reject(Error(data.error))}catch{reject(Error('업로드 응답을 확인할 수 없습니다.'))}};xhr.onerror=()=>reject(Error('서버에 연결하지 못했습니다.'));xhr.send(file.value)});modal.value=false;await refresh();await open(row)}catch(e){error.value=e.message}finally{uploading.value=false}}
function spaceKey(event){
if(event.key!==' '||!selected.value||modal.value||downloadDialog.value||logoutDialog.value||event.ctrlKey||event.metaKey||event.altKey)return;
if(event.target.closest?.('input:not([type=range]),textarea,select,[contenteditable]'))return;
event.preventDefault();event.stopPropagation();
if(event.type==='keydown'&&!event.repeat&&!loading.value)toggle()}
onMounted(()=>{if(props.user){refresh();timer=setInterval(refresh,1800);}window.addEventListener('resize',draw);window.addEventListener('keydown',spaceKey,true);window.addEventListener('keyup',spaceKey,true)});
onBeforeUnmount(()=>{clearMetadata();disposed=true;buffers.clear();loadController?.abort();revision++;stop();clearMedia();clearInterval(timer);window.removeEventListener('resize',draw);window.removeEventListener('keydown',spaceKey,true);window.removeEventListener('keyup',spaceKey,true);context?.close()});
</script>

<template>
<div class="studio" @pointerdown="press" :class="{'is-playing':playing}">
<aside class="sidebar"><a class="brand" href="#" @click.prevent="go('home',$event)"><span class="logo">≋</span><span>music<span class="brand-thin">analyzer</span><small>YOUR SOUND, UNLAYERED.</small></span></a><div class="workspace-label">MENU</div><button class="nav" :class="{active:page==='home'}" @click="go('home',$event)"><span>⌂</span>홈</button><button class="nav" :class="{active:page==='library'}" @click="go('library',$event)"><span>♫</span>라이브러리<b class="nav-count">{{completed}}</b></button><div class="side-bottom"><span class="online-dot"></span> 로컬 스튜디오<small>음원은 이 PC에서 처리됩니다.</small></div></aside>
<main>
<header class="topbar"><div><span class="crumb">워크스페이스</span><span class="slash">/</span><span>{{selected?'트랙 스튜디오':page==='library'?'라이브러리':'홈'}}</span></div><div class="top-right"><template v-if="user"><span class="account-name">{{user.display_name}}</span><button class="button small" :disabled="accountBusy" :aria-busy="accountBusy" @click="modalOrigin=originOf($event);logoutDialog=true">{{accountBusy?'로그아웃 중…':'로그아웃'}}</button></template><button v-else data-account-login class="button small" @click="emit('login',$event)">로그인</button><span class="status-pill"><i></i> Local engine</span><button class="button small" @click="newAnalysis">＋ 새 분석</button></div></header>
<div v-if="error&&!modal" role="alert" class="error">{{error}}<button @click="error=''">닫기</button></div>
<Transition :css="false" mode="out-in" @enter="pageEnter" @leave="pageLeave" @after-enter="draw"><section v-if="!selected" :key="page" class="home">
<template v-if="page==='library'">
<div class="page-heading"><h1>라이브러리</h1><p>분석을 마친 곡을 선택해 트랙을 확인하세요.</p></div>
<div class="library-heading"><div><h2>내 분석 라이브러리 <span>{{rows.length}}</span></h2><p>내 계정으로 분석한 곡과 분리된 트랙을 확인하세요.</p></div><label v-if="user" class="search"><span>⌕</span><input v-model="search" placeholder="곡 이름 검색" aria-label="곡 이름 검색"></label></div>
<div class="library"><div class="table-header"><span>곡 이름</span><span>분석 구성</span><span>길이</span><span>상태</span><span></span></div><button v-for="(row,i) in filtered" :key="row.id" class="library-row" @click="visit(row,$event)"><div class="song-cell"><div class="song-icon" :style="{'--accent':['#b39bfa','#74c9b1','#8ab5e5','#dda778'][i%4]}">≋</div><div><strong>{{row.name}}</strong><small>{{row.track_count}} tracks <span>·</span> {{typeof row.created==='string'?row.created.slice(0,10):'이전 분석'}}</small></div></div><span class="model-label">{{modelName(row.model,row.separation_version)}}</span><span class="duration">{{stamp(row.duration)}}</span><span class="badge" :class="row.state">{{stateName(row.state)}}<span v-if="row.state==='RUNNING'"> · {{row.progress}}%</span></span><span class="arrow">↗</span></button><div v-if="!filtered.length" class="empty"><template v-if="!user">로그인하면 내 분석 결과를 확인할 수 있습니다. <button class="button small" @click="emit('login',$event)">로그인하기</button></template><template v-else>{{search?'검색 결과가 없습니다.':'아직 분석한 곡이 없습니다. 첫 음원을 추가해 보세요.'}}</template></div></div></template>
<template v-else>
<div class="page-heading"><span class="eyebrow">MUSIC ANALYZER</span><h1>음악을, <em>한 트랙씩.</em></h1><p>보컬만, 드럼만, 기타만. 듣고 싶은 소리만 골라 들을 수 있어요.</p></div>
<div class="hero"><div class="hero-copy"><h2>곡에서 소리를 분리하세요!</h2><p>음원 한 곡을 올리면 보컬, 드럼, 베이스, 기타까지 파트별로 나눠 줘요.<br>2·6·13트랙 중에 골라서 따로 듣고, 파일로 받아 갈 수 있어요.</p><button class="button white" @click="newAnalysis">＋ 새 분석 만들기 <span>↗</span></button><div class="hero-tags">MP3 · WAV · FLAC <span>최대 15분</span></div></div><div class="hero-art" aria-hidden="true"><div v-for="(color,i) in ['#c6b2ff','#72d5b5','#edaf72','#88b8ff','#e2c77f']" :key="color" class="art-track" :style="{'--tint':color,transform:'translateX('+(i%2?25:0)+'px)'}"><span class="art-dot"></span><div class="art-wave"><i v-for="n in 58" :key="n" :style="{height:(8+Math.abs(Math.sin(n*2.7+i)*Math.cos(n*.2+i))*35)+'px'}"></i></div></div><div class="art-playhead"></div><div class="art-badge">2 / 6 / 13 tracks <span>◉</span></div></div></div>
<section class="lp about-lp"><div class="about-top"><div class="about-left"><span class="eyebrow">ABOUT</span><h2>음원에서 파트별 소리를 <em>따로 뽑아 주는 서비스</em></h2></div><div class="about-right"><div class="about-points"><article><h3>이런 서비스예요</h3><p>한 곡에 섞여 있는 보컬과 악기를 AI가 파트별로 나눠요.<br>결과는 트랙 하나하나가 따로 재생되는 오디오 파일이에요.</p></article><article><h3>이렇게 쓰여요</h3><p>보컬만 빼고 연습하거나, 베이스·기타 파트를 귀로 따거나<br>드럼만 들으며 편곡을 분석할 수 있어요.</p></article><article><h3>이런 점이 달라요</h3><p>2·6·13트랙 중에서 고를 수 있고, 원곡을 함께 살펴서<br>엉뚱한 트랙에 섞인 소리를 바로잡아요.</p></article></div>
</div></div><div class="about-flow"><div class="flow-in"><span class="flow-label">올린 음원</span><div class="lane" style="--tint:#c7ccd9"><span class="lane-dot"></span><b>원곡</b><div class="lane-wave"><i v-for="n in 160" :key="n" :style="{height:(8+Math.abs(Math.sin(n*1.3)*Math.cos(n*.21)+Math.sin(n*.7)*.5)*14)+'px'}"></i></div></div></div><span class="flow-arrow">→</span><div class="flow-out"><span class="flow-label">분리된 트랙</span><div v-for="(t,i) in [['보컬','vocals'],['드럼','drums'],['베이스','bass'],['기타','guitar'],['피아노','piano']]" :key="t[0]" class="lane" :style="{'--tint':colors[t[1]]}"><span class="lane-dot"></span><b>{{t[0]}}</b><div class="lane-wave"><i v-for="n in 160" :key="n" :style="{height:(5+Math.abs(Math.sin(n*1.9+i*2.3)*Math.cos(n*.37+i))*18)+'px'}"></i></div></div></div></div>
</section>
<section class="lp plans-lp"><div class="lp-head"><span class="eyebrow">TRACK PLANS</span><h2>용도에 따라 다른게 분리할 수 있어요</h2></div><div class="lp-body"><div class="plan-split"><div class="plan-side"><article v-for="c in compare.slice(0,2)" :key="c.id"><b>{{c.title}}</b><div><h3>{{c.lead}}</h3><p>{{c.text}}</p><div class="recommend"><ul><li v-for="f in c.fit.split(' · ')" :key="f">{{f}}</li></ul></div></div><div class="plan-lanes"><div v-for="(t,i) in c.tracks" :key="t[0]" class="lane" :style="{'--tint':colors[t[1]]||'#9a8bd0','--d':i*45+'ms'}"><span class="lane-dot"></span><b>{{t[0]}}</b><div class="lane-wave"><i v-for="n in 160" :key="n" :style="{height:(5+Math.abs(Math.sin(n*1.9+i*2.3)*Math.cos(n*.37+i))*18)+'px'}"></i></div></div></div></article></div>
<div class="plan-panel" v-for="c in compare.slice(2)" :key="c.id"><div class="plan-info"><b class="plan-big">{{c.title}}</b><h3>{{c.lead}}</h3><p>{{c.text}}</p><div class="recommend"><ul><li v-for="f in c.fit.split(' · ')" :key="f">{{f}}</li></ul></div></div><div class="plan-lanes"><div v-for="(t,i) in c.tracks" :key="t[0]" class="lane" :style="{'--tint':colors[t[1]]||'#9a8bd0','--d':i*45+'ms'}"><span class="lane-dot"></span><b>{{t[0]}}</b><div class="lane-wave"><i v-for="n in 160" :key="n" :style="{height:(5+Math.abs(Math.sin(n*1.9+i*2.3)*Math.cos(n*.37+i))*18)+'px'}"></i></div></div></div></div></div>
</div></section>
<section class="lp feature-lp"><div class="lp-head"><span class="eyebrow">STUDIO</span><h2>음악 작업 프로그램처럼 트랙을 다뤄요</h2></div><div class="lp-body"><div class="studio-split"><div class="studio-list"><div v-for="f in studioFeatures" :key="f[0]" class="studio-item"><span class="studio-glyph" :class="f[3]">{{f[0]}}</span><div><h3>{{f[1]}}</h3><p>{{f[2]}}</p></div></div></div><figure class="shot"><div class="shot-bar"><i></i><i></i><i></i></div><img src="/studio-tracks.png" alt="트랙 스튜디오 실제 화면" width="588" height="496" loading="lazy"></figure></div></div></section>
<section class="lp steps-lp"><div class="lp-head"><span class="eyebrow">HOW IT WORKS</span><h2>사용 방법</h2></div><div class="lp-body"><ol class="steps-line"><li v-for="(t,i) in howTo" :key="t[0]"><b>{{i+1}}</b><h3>{{t[0]}}</h3><p>{{t[1]}}</p></li></ol></div></section>
<div class="cta-band"><div><h3>첫 곡을 올려 보세요</h3><p>MP3 · WAV · FLAC, 최대 15분</p></div><button class="button white" @click="user?go('library',$event):emit('login',$event)">{{user?'내 라이브러리 열기 ↗':'로그인하고 시작하기 ↗'}}</button></div>
</template>
<footer class="home-footer">CREATED FOR LISTENING. BUILT FOR EXPLORING.<span>Music Analyzer / Local workspace</span></footer>
</section>
<section v-else :key="selected.id" class="session">
<button class="back" @click="home">← 라이브러리로 돌아가기</button>
<div class="session-heading"><div><h1>{{selected.name}}</h1><p><template v-if="selected.vocal_source==='roformer'&&selected.model!=='final_10'">보컬 RoFormer <span>+</span> 악기 </template>{{modelName(selected.model,selected.separation_version)}} <span>·</span> {{stamp(duration)}} <span>·</span> {{selected.track_count}} 트랙<template v-if="tracks.some(t=>t.reference)"> <span>+</span> 원본</template></p></div><div v-if="selected.archive_url" class="session-actions"><button v-if="!['basic_2','basic_6'].includes(selected.model)&&tracks.some(t=>t.family==='vocals')&&!tracks.some(t=>t.family==='lead')" class="button small" :disabled="loading" @click="splitVocals">보컬 세부분리</button><label class="clarity-toggle"><span>선명도</span><input v-model="clarity" type="checkbox" role="switch" aria-label="선명도 후처리" @change="toggleClarity"><i></i></label><div class="clarity-knob-control" :class="{disabled:!clarity}"><div class="clarity-knob" role="slider" :tabindex="clarity?0:-1" :aria-disabled="!clarity" :aria-label="'전체 선명도 강도'" aria-valuemin="0" aria-valuemax="100" :aria-valuenow="clarityControl.clarityStrength" :aria-valuetext="clarityControl.clarityStrength+'%'" :style="{'--knob-angle':(clarityControl.clarityStrength*2.7-135)+'deg','--knob-fill':clarityControl.clarityStrength*2.7+'deg'}" @pointerdown.prevent="clarity&&knobDown($event,clarityControl)" @pointermove="clarity&&knobMove($event,clarityControl)" @keydown="clarity&&knobKey($event,clarityControl)"><i></i></div><span>선명도 <b>{{clarityControl.clarityStrength}}%</b><small v-if="!clarity" class="knob-off-label">OFF</small></span></div><button class="button" @click="downloadChoice(null,$event)">↓ 전체 트랙 다운로드</button></div></div>
<div v-if="selected.state!=='SUCCEEDED'" class="processing"><div v-if="selected.state!=='FAILED'" class="spinner"></div><div v-else class="failed-symbol">!</div><span class="tiny-label">ANALYSIS SESSION</span><h2>{{selected.stage}}</h2><p v-if="selected.state!=='FAILED'">{{versions.find(v=>v.id===selected.model)?.note||'선택한 구성으로 음원을 분리합니다.'}}</p><p v-else>{{selected.error}}</p><div class="progress-line"><i :style="{width:selected.progress+'%'}"></i></div><div class="progress-caption"><span>{{selected.total_chunks?((selected.completed_chunks||0)+' / '+selected.total_chunks+' 구간'):'현재 단계 준비 및 처리 중'}}</span><b>{{selected.progress}}%</b></div><div class="stage-steps"><template><span v-for="([label,end],i) in analysisSteps" :key="label" :class="{done:selected.progress>=end,current:selected.progress<end&&(i===0||selected.progress>=analysisSteps[i-1][1])}">{{String(i+1).padStart(2,'0')}} {{label}}</span></template></div></div>
<template v-else>
<div v-if="loading" class="track-loading" role="status" aria-live="polite" aria-busy="true">
<div class="spinner"></div><h2>트랙을 준비하고 있습니다</h2><p>{{loadStage}}</p>
<div class="progress-line"><i :style="{width:(tracks.length?loaded/tracks.length*100:0)+'%'}"></i></div>
<div class="progress-caption"><span>{{loaded}} / {{tracks.length||selected.track_count||'—'}} 트랙</span><b>{{tracks.length?Math.round(loaded/tracks.length*100):0}}%</b></div>
</div>
<div v-else-if="tracks.length&&loaded!==tracks.length" class="track-loading"><h2>트랙을 불러오지 못했습니다</h2><button class="button" @click="open(selected)">다시 불러오기</button></div>
<template v-else>
<div class="transport master-row"><div class="master-left"><span class="master-label">전체</span><button :class="{selected:allMuted,partial:anyMuted&&!allMuted}" @click="masterToggle('mute',anyMuted)" aria-label="전체 음소거" :aria-pressed="allMuted?'true':anyMuted?'mixed':'false'" :title="anyMuted?'눌려 있는 음소거를 모두 해제':'모든 트랙 음소거'">M</button><button :class="{selected:allSolo,partial:anySolo&&!allSolo}" @click="masterToggle('solo',anySolo)" aria-label="전체 솔로" :aria-pressed="allSolo?'true':anySolo?'mixed':'false'" :title="anySolo?'눌려 있는 솔로를 모두 해제':'모든 트랙 솔로'">S</button></div><div class="master-main"><div class="play-controls"><button class="reset" aria-label="처음으로" @click="stop();position=0">↤</button><button class="play" :disabled="loading" @click="toggle" :aria-label="starting?'재생 준비 취소':playing?'일시정지':'재생'">{{loading||starting?'◌':playing?'Ⅱ':'▶'}}</button><button class="reset" aria-label="모든 볼륨 기본값으로" title="모든 볼륨 기본값으로" @click="resetVolumes">↻</button><div class="time"><strong>{{stamp(position)}}</strong><span>/ {{stamp(duration)}}</span></div></div><div class="transport-right"><span v-if="loading" class="loading-text">트랙 불러오는 중 {{loaded}} / {{tracks.length}}</span><span class="rate">44.1 kHz <span>STEREO</span></span><label class="master">마스터<input v-model.number="master" type="range" min="0" max="2" step=".01" @input="mix" @dblclick="master=1;mix()" title="더블클릭하여 기본 음량(100%)으로 복원" aria-label="마스터 음량" :aria-valuetext="Math.round(master*100)+'%'"><span>{{Math.round(master*100)}}%</span></label></div></div><span></span></div>
<div class="daw" :aria-busy="starting" :class="{'daw-playing':playing,'has-clarity':clarity,'daw-buffering':starting}"><div v-if="starting" class="track-buffer-overlay" role="status" aria-live="polite"><div class="track-buffer-card"><span class="buffer-spinner"></span><strong>재생 구간 준비 중…</strong><span>{{stamp(position)}} · 전체 트랙</span></div></div>
<div class="daw-ruler"><span>TRACKS <b>{{tracks.length}}</b></span><div class="ruler-scale"><i v-for="tick in rulerTicks" :key="tick.t" :style="{left:tick.left+'%'}">{{tick.t}}s</i><input class="timeline" type="range" :value="position" min="0" :max="duration" step=".1" @input="seek" aria-label="재생 위치"><div class="ruler-head" :style="{left:(position/duration*100)+'%'}"></div></div><span></span></div>
<div v-for="(track,i) in visibleTracks" :key="track.family" class="track-row" :style="{'--track':colors[track.family]||'#8da9d7','--index':i}" :class="{muted:track.mute,solo:track.solo}">
<div class="track-info"><div class="track-title"><span class="track-icon" aria-hidden="true"><Drum v-if="track.family==='drums'" :size="22" :stroke-width="1.8"/><svg v-else viewBox="0 0 24 24"><path :d="trackIcons[track.family]||mdiMusicNote"/></svg></span><b>{{trackTitle(track)}}</b><span class="track-format">{{track.reference?'REF':'WAV'}}</span></div><div class="track-settings"><button :class="{selected:track.mute}" @click="track.mute=!track.mute;mix()" :aria-label="trackTitle(track)+' 음소거'" :aria-pressed="track.mute">M</button><button :class="{selected:track.solo}" @click="track.solo=!track.solo;mix()" :aria-label="trackTitle(track)+' 솔로'" :aria-pressed="track.solo">S</button><input v-model.number="track.volume" type="range" min="0" max="2" step=".01" @input="mix" @dblclick="track.volume=1;mix()" title="더블클릭하여 기본 음량(100%)으로 복원" :aria-label="trackTitle(track)+' 음량'"><span>{{Math.round(track.volume*100)}}%</span></div></div>
<div class="waveform" @click="seekWave"><canvas :data-wave="track.family"></canvas><div class="playhead" :style="{left:(position/duration*100)+'%'}"></div></div><button class="track-download" @click="downloadChoice(track,$event)" :aria-label="trackTitle(track)+' WAV 다운로드'">↓</button></div>
<div v-if="loading&&!tracks.length" class="empty">파형을 준비하고 있습니다…</div>
</div><div class="session-foot"><span>원본은 기본 음소거입니다. 원본의 S 버튼으로 분리 결과와 비교하세요.</span><span>다운로드는 원본 FLOAT WAV · 음량 조절은 재생에만 적용</span></div>
</template></template></section></Transition>
</main>
<Transition :css="false" @enter="modalEnter" @leave="modalLeave"><div v-if="modal" class="modal-backdrop" @click.self="!uploading&&(modal=false)" @keydown.esc="!uploading&&(modal=false)">
<form class="modal analysis-modal" :class="{'has-version':uploadStep===2&&chosenVersion,'is-upload-step':uploadStep===1,'is-version-step':uploadStep===2}" role="dialog" aria-modal="true" aria-labelledby="modal-title" @submit.prevent="submit">
<div class="modal-top"><button type="button" class="close" @click="modal=false" :disabled="uploading" aria-label="닫기">×</button></div>
<nav class="upload-tabs" aria-label="새 분석 단계"><button type="button" :class="{active:uploadStep===1}" :disabled="uploading" @click="uploadStep=1">1. 파일 업로드</button><button type="button" :class="{active:uploadStep===2}" :disabled="!file||readingFile||uploading" @click="uploadStep=2">2. 버전 선택</button></nav>
<h2 id="modal-title">{{uploadStep===1?'음원을 업로드하세요.':'어떤 트랙으로 추출할까요?'}}</h2>
<Transition name="analysis-tab" mode="out-in"><section v-if="uploadStep===1" key="upload" class="analysis-tab-panel"><p>음원을 선택한 다음 추출 버전을 골라 주세요.</p><label class="dropzone" @dragover.prevent @drop.prevent="choose"><input type="file" accept=".mp3,.wav,.flac" @change="choose" :disabled="uploading" aria-label="음원 파일 선택"><span class="upload-symbol">↥</span><strong>{{file?file.name:'음원을 드래그하거나 클릭해 선택'}}</strong><small>{{file?(file.size/1024/1024).toFixed(1)+' MB':'MP3, WAV, FLAC · 최대 1GB / 15분'}}</small></label><p class="modal-note" aria-live="polite">{{readingFile?'곡 길이를 확인하고 있습니다…':fileDuration?'곡 길이 '+stamp(fileDuration):file?'곡 길이를 읽지 못했습니다. 분석은 진행할 수 있습니다.':'파일을 선택하면 곡 길이를 확인합니다.'}}</p></section>
<section v-else key="versions" class="analysis-tab-panel"><div class="version-layout"><div class="version-selection"><p class="selected-file"><strong>{{file?.name}}</strong><span>{{fileDuration?'곡 길이 '+stamp(fileDuration):'곡 길이 확인 불가'}}</span></p><div class="version-options" role="radiogroup" aria-label="추출 버전"><label v-for="version in versions" :key="version.id" class="version-option" :class="{selected:preset===version.id}"><input type="radio" name="analysis-version" v-model="preset" :value="version.id"><span><strong>{{version.title}}</strong><span>{{version.description}}</span><span class="version-estimate" v-if="versionEstimate(version.id)">예상 분석시간 · {{formatEstimate(versionEstimate(version.id).low)}} ~ {{formatEstimate(versionEstimate(version.id).high)}}<small>{{versionEstimate(version.id).basis}}</small></span><span class="version-estimate" v-else>예상 분석시간 · 곡 길이 확인 필요</span><small>{{version.note}}</small></span></label></div><p class="modal-note">예상시간은 참고 범위이며, 업로드·대기시간은 제외됩니다. 실제 처리시간은 달라질 수 있습니다.</p></div><Transition name="version-details"><aside v-if="chosenVersion" class="version-detail-panel" aria-live="polite"><Transition name="detail-content" mode="out-in"><div :key="chosenVersion.id"><span class="detail-eyebrow">분리 과정</span><h3>{{chosenVersion.title}} 분석</h3><p>{{chosenVersion.note}}</p><ol class="version-steps" tabindex="0" aria-label="분리 과정 목록"><li v-for="[label,,description] in chosenVersion.steps" :key="label"><b>{{label}}</b><span>{{description}}</span></li></ol></div></Transition></aside></Transition></div></section></Transition>
<div v-if="error" role="alert" class="error">{{error}}</div><div v-if="uploading" class="upload-state"><span>음원 올리기 중</span><b>{{uploadPercent}}%</b><div class="progress-line"><i :style="{width:uploadPercent+'%'}"></i></div></div><button class="button full" type="submit" :disabled="uploading||(uploadStep===1?(!file||readingFile):(!file||!chosenVersion))">{{uploading?'음원 올리기 중…':uploadStep===1?'다음 · 버전 선택':'분석 시작하기'}} <span>→</span></button></form>
</div></Transition>
<Transition :css="false" @enter="modalEnter" @leave="modalLeave"><div v-if="logoutDialog" class="modal-backdrop" @click.self="logoutDialog=false" @keydown.esc="logoutDialog=false"><div class="modal confirm-modal" role="alertdialog" aria-modal="true" aria-labelledby="logout-title"><h2 id="logout-title">로그아웃하시겠습니까?</h2><div class="confirm-actions"><button type="button" class="button small confirm-cancel" @click="logoutDialog=false">취소</button><button type="button" class="button small" @click="logoutDialog=false;emit('logout')">로그아웃</button></div></div></div></Transition>
<Transition :css="false" @enter="modalEnter" @leave="modalLeave"><div v-if="downloadDialog" class="modal-backdrop" @click.self="downloadDialog=null" @keydown.esc="downloadDialog=null"><div class="modal download-modal" role="dialog" aria-modal="true" aria-labelledby="download-title"><div class="modal-top"><span class="tiny-label">DOWNLOAD TRACKS</span><button class="close" aria-label="다운로드 창 닫기" @click="downloadDialog=null">×</button></div><h2 id="download-title">어떤 파일로 받을까요?</h2><p>{{downloadDialog.name}} · 선명도 처리에는 현재 노브 값을 적용합니다.</p><div class="download-values"><span v-for="t in downloadDialog.tracks" :key="t.family">{{names[t.family]}} {{t.strength}}%</span></div><a class="download-option" :href="downloadUrl('enhanced')">선명도 처리된 파일 <small>현재 설정을 적용한 WAV{{downloadDialog.single?'':' ZIP'}}</small><b>↗</b></a><a class="download-option" :href="downloadUrl('raw')">그냥 받기 <small>선명도 적용 전 분리음</small><b>↗</b></a><a class="download-option" :href="downloadUrl('both')">둘 다 받기 <small>분리음과 선명도 처리음을 폴더별로 담은 ZIP</small><b>↗</b></a></div></div></Transition>
</div>
</template>
