<script setup>
import {ref,computed,watch,onMounted,onBeforeUnmount,nextTick} from 'vue';
import {Drum} from '@lucide/vue';
import SamplePlayer from './SamplePlayer.vue';
import SiteFooter from './SiteFooter.vue';
import {versions,compare,isBeta,betaNotice,betaResultNote,defaultSteps,versionFor} from './versions';
import {mdiBellRing,mdiMicrophone,mdiAccountGroup,mdiPiano,mdiTune,mdiViolin,mdiTrumpet,mdiGuitarAcoustic,mdiGuitarElectric,mdiWaveform,mdiDisc,mdiMusicNote} from '@mdi/js';
import {estimateAnalysis,formatEstimate} from './analysisEstimate';
import {trackLevels} from './trackGroups';
import {BufferedPlayer} from './bufferPlayer';
import {originOf,expand,collapse,press,settled} from './motion';
const props=defineProps({user:{type:Object,default:null},accountBusy:{type:Boolean,default:false}});
const emit=defineEmits(['logout','login','withdraw']);
let modalOrigin,pageOrigin,backdropDown=false; // close only when the press also started on the backdrop (drag-selecting text out of a modal must not close it)
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
const page=ref('home'),rows=ref([]),selected=ref(null),modal=ref(false),file=ref(null),preset=ref(''),uploadStep=ref(1),uploading=ref(false),uploadPercent=ref(0),error=ref(''),search=ref(''),loading=ref(false),tracks=ref([]),playing=ref(false),position=ref(0),master=ref(1),loop=ref(false),loaded=ref(0),loadStage=ref(''),exporting=ref(''),logoutDialog=ref(false),withdrawDialog=ref(false),deleteDialog=ref(null),deleting=ref(false),rights=ref(false),legalVersions=ref(null),rightsDialog=ref(false),releaseInfo=ref(null);
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
const faqTab=ref(0),faqOpen=ref(-1);
const faq=[
{tab:'서비스',items:[
['Music Analyzer는 어떤 서비스인가요?','음원 파일을 올리면 보컬과 악기를 파트별로 나눠 주는 음원 분리 서비스예요. 나뉜 트랙은 웹의 트랙 스튜디오에서 바로 들어 보고, 필요한 트랙만 골라 WAV 파일로 내려받을 수 있어요. 보컬을 뺀 반주로 연습하거나, 기타나 베이스 파트를 귀로 따거나, 편곡을 악기별로 뜯어 보고 싶을 때 쓰시면 좋아요.'],
['어떤 파일을 올릴 수 있나요?','MP3, WAV, FLAC 파일을 올릴 수 있어요. 파일 크기는 1GB 이하, 곡 길이는 15분 이하여야 해요. 영상 파일은 지원하지 않으니 오디오 파일로 변환해서 올려 주세요.'],
['음질은 어떻게 처리되나요?','분석을 시작하면 올린 음원을 44.1kHz 스테레오 WAV로 맞춘 뒤 처리해요. 나뉜 트랙도 같은 형식의 WAV(32비트 부동소수점)로 받을 수 있어서, 다른 음악 작업 프로그램에 바로 가져가 쓸 수 있어요.'],
['어떤 음원을 올릴 수 있나요?','직접 제작했거나 본 서비스를 이용해 저장·분석·변환할 수 있는 권리 또는 적법한 이용 권한이 있는 음원을 사용해 주세요. 분리 결과의 이용 가능 범위는 원곡과 음원에 적용되는 권리 및 이용 조건에 따라 달라질 수 있습니다.'],
['분리한 트랙을 영상·공연·리믹스 등에 사용할 수 있나요?','분리 결과를 공개·배포·공연·영상 제작·리믹스 또는 상업적인 목적으로 이용하는 경우, 원곡 및 음원에 관한 별도의 이용 권한이 필요할 수 있습니다. Music Analyzer를 이용했다는 사실 자체가 원곡에 대한 별도의 저작권 이용허락을 의미하지 않습니다.'],
['분리된 파일은 원래 스튜디오 멀티트랙인가요?','아니요. Music Analyzer의 결과는 완성된 음원을 AI가 분석해 각 파트의 소리를 추정하여 분리한 오디오입니다. 원래 녹음·믹싱 과정에서 만들어진 스튜디오 멀티트랙과는 다르며, 곡에 따라 다른 악기의 소리, 잔향 또는 음질 변화가 일부 포함될 수 있습니다.'],
['모든 곡에서 같은 품질로 분리되나요?','아니요. 악기 구성, 믹싱 방식, 음질, 음량, 리버브와 이펙트 등에 따라 분리 결과가 달라질 수 있습니다. 특히 서로 비슷한 음색의 악기나 원곡에서 작게 들리는 악기는 다른 트랙에 섞이거나 일부 누락될 수 있습니다.']]},
{tab:'분석 구성',items:[
['2트랙, 6트랙, 13트랙은 어떻게 다른가요?','2트랙은 보컬과 전체 반주로 나눠요. 6트랙은 보컬, 기타, 베이스, 드럼, 피아노, 추가 반주로 나누고, 기타는 통기타와 일렉을 구분하지 않아요. 13트랙은 보컬과 코러스를 나누고 신디사이저, 스트링, 브라스, 통기타, 일렉기타까지 더 세부적으로 나누는 BETA(연구 중) 기능이에요.'],
['어떤 구성을 고르면 좋을까요?','보컬을 빼고 반주로 연습하거나 곡 구조를 들어 보려면 2트랙이 가장 빠르고 간단해요. 밴드 파트를 연습하거나 한 악기만 골라 듣고 싶으면 6트랙이 알맞아요. 세부 악기까지 확인해 보고 싶다면 13트랙(BETA)을 사용해 보세요. 결과는 직접 들어 보고 판단해 주세요.'],
['13트랙은 2트랙이나 6트랙보다 더 정확한가요?','반드시 그렇지는 않습니다. 13트랙은 더 많은 악기를 세부적으로 나누기 위한 실험 기능입니다. 현재 2트랙과 6트랙은 비교적 안정화되어 있지만, 13트랙은 신디사이저·스트링·브라스·기타 등 음색이 겹치는 악기에서 오분류나 다른 트랙의 소리가 섞이는 현상이 발생할 수 있습니다. 세부 파트를 확인해야 할 때 사용하고 결과를 직접 들어보는 것을 권장합니다.'],
['13트랙의 추가 반주, 기타 보조, 기타 타악기는 무엇인가요?','어느 악기로도 분류되지 않은 나머지 소리는 추가 반주에 모여요. 기타 보조는 기타 계열에서 통기타나 일렉기타로 분류하지 못하고 남은 소리예요. 종소리나 팀파니 같은 타악기는 드럼과 별도로 기타 타악기 트랙에 담겨요.'],
['분석에는 시간이 얼마나 걸리나요?','곡 길이와 고른 구성에 따라 달라요. 트랙이 많을수록 더 오래 걸려요. 새 분석 화면에서 음원을 고르면 구성별 예상 시간을 미리 볼 수 있고, 분석이 시작되면 진행률이 표시돼요.']]},
{tab:'스튜디오',items:[
['트랙 스튜디오에서는 무엇을 할 수 있나요?','트랙마다 음소거(M), 솔로(S), 볼륨 조절을 할 수 있어요. 맨 위의 전체 줄에서는 모든 트랙의 음소거와 솔로를 한 번에 풀 수 있고, 한 번 더 누르면 풀기 전 상태로 돌아가요. 볼륨 초기화 버튼은 모든 트랙의 볼륨을 100%로 되돌려요. 스페이스바로 재생과 정지를 할 수 있고, 재생바를 눌러 원하는 구간으로 바로 이동해요.'],
['스튜디오에 보이는 원본 트랙은 무엇인가요?','분리 결과와 비교해 들을 수 있도록 올린 음원을 그대로 넣어 둔 트랙이에요. 기본으로 음소거되어 있고, 원본의 S 버튼을 눌러 분리된 트랙들과 번갈아 들어 볼 수 있어요.'],
['분리된 트랙은 어떻게 내려받나요?','트랙 오른쪽의 다운로드 버튼으로 한 트랙만 받거나, 위쪽의 전체 트랙 다운로드로 모든 트랙을 ZIP으로 한 번에 받을 수 있어요. 스튜디오에서 조절한 볼륨은 재생에만 적용되고 다운로드 파일에는 반영되지 않아요.'],
['분리된 소리에 다른 악기가 섞여 들리기도 하나요?','네, 음원에 따라 일부 소리가 다른 트랙에 섞일 수 있어요. 소리가 작은 악기나 신디 패드처럼 다른 악기와 비슷하게 들리는 소리는 특히 구분이 어려워요. 이런 경우에는 구성을 바꿔 다시 분석해 보시거나, 트랙을 함께 들으며 필요한 쪽을 골라 쓰시길 권해요.']]},
{tab:'계정',items:[
['로그인이 꼭 필요한가요?','홈 화면은 누구나 볼 수 있지만, 새 분석을 만들고 내 라이브러리를 보려면 로그인이 필요해요. 처음이라면 회원가입 후 바로 이용할 수 있어요.'],
['내 분석은 다른 사람에게 보이나요?','아니요. 분석한 곡과 나뉜 트랙은 내 계정의 라이브러리에만 보여요.'],
['업로드한 음원은 AI 학습에 사용되나요?','아니요. Music Analyzer는 사용자가 업로드한 음원과 생성된 분리 결과를 AI 모델 학습 또는 학습 데이터셋 제작에 사용하지 않습니다.'],
['분석이나 계정을 삭제할 수 있나요?','네. 라이브러리와 트랙 스튜디오에서 분석을 삭제할 수 있고, 상단의 회원 탈퇴로 계정과 개인 분석 라이브러리를 삭제할 수 있어요. 삭제한 내용은 복구할 수 없어요.'],
['분석 중에 창을 닫아도 되나요?','분석은 서버에서 진행돼요. 다시 접속해서 라이브러리를 열면 진행 중인 분석과 진행률을 확인할 수 있고, 끝난 곡은 그대로 이어서 들어 볼 수 있어요.']]}];
const studioFeatures=[['M','트랙별 음소거','듣기 싫은 트랙만 끌 수 있어요.','is-m','#af8fff'],['S','트랙별 솔로','원하는 트랙 소리만 따로 들어요.','is-s','#6ad6b3'],['V','볼륨 조절','더블클릭시 기본값으로 돌아가요.','is-v','#e6c66d'],['R','전체 해제','켜진 음소거·솔로를 한 번에 풀고, 다시 누르면 이전 상태로 돌아가요.','is-r','#b6a2ff'],['U','볼륨 초기화','모든 트랙 볼륨을 한 번에 100%로 되돌려요.','is-u','#b6a2ff'],['P','재생과 이동','스페이스바로 재생·정지, 재생바를 눌러 원하는 구간으로 가요.','is-p','#b6a2ff'],['D','WAV 다운로드','트랙 하나만, 또는 전체를 한 번에 받아요.','is-d','#73a9ff']];
const filtered=computed(()=>rows.value.filter(r=>r.name.toLowerCase().includes(search.value.toLowerCase())));
const PER=10,libPage=ref(1);
const pageCount=computed(()=>Math.max(1,Math.ceil(filtered.value.length/PER)));
const paged=computed(()=>filtered.value.slice((Math.min(libPage.value,pageCount.value)-1)*PER,Math.min(libPage.value,pageCount.value)*PER));
watch(search,()=>libPage.value=1);
const pageNums=computed(()=>{const n=pageCount.value,c=Math.min(libPage.value,n);return [...new Set([1,n,c-1,c,c+1])].filter(p=>p>=1&&p<=n).sort((a,b)=>a-b)});
const active=computed(()=>rows.value.filter(r=>['QUEUED','RUNNING'].includes(r.state)));
const completed=computed(()=>rows.value.filter(r=>r.state==='SUCCEEDED').length);
const duration=computed(()=>selected.value?.duration||0);
const offered=computed(()=>versions.filter(v=>!releaseInfo.value?.presets||releaseInfo.value.presets.includes(v.commercial)));
const chosenVersion=computed(()=>offered.value.find(v=>v.id===preset.value));
const analysisSteps=computed(()=>versionFor(selected.value?.model)?.steps||defaultSteps);
// The server's free-text stage names describe internal processing; the screen only names the generic step the progress is in.
const stageTitle=computed(()=>{const row=selected.value;if(!row)return'';if(row.state==='FAILED')return'분석 실패';if(row.state==='QUEUED')return'분석 대기 중';const steps=analysisSteps.value,step=steps.find(item=>(row.progress||0)<item.end)||steps.at(-1);return step.label+' 중'});

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
const modelName=(m,v)=>m==='final_11'&&v&&!['staged-context-percussion-v11','staged-context-percussion-v12','staged-context-strings-v13','staged-context-backing-v14','staged-context-families-v15','staged-context-pads-v16'].includes(v)?'12트랙 분리':({basic_2:'2트랙 분리',basic_6:'6트랙 분리',commercial_2:'2트랙 분리',commercial_6:'6트랙 분리',final_11:'13트랙 분리',commercial_13:'13트랙 분리',final_10:'악기별 분리'}[m]||'분석');
const stateName=s=>({SUCCEEDED:'완료',RUNNING:'분석 중',QUEUED:'대기 중',FAILED:'실패',CANCELLED:'취소'}[s]||s);
async function request(url,options){const r=await fetch(url,{...options,headers:{...options?.headers,'X-Requested-With':'MusicAnalyzer'}});if(r.status===401)window.dispatchEvent(new Event('music-session-expired'));if(!r.ok){const d=await r.json();throw Error(d.error||'요청을 처리하지 못했습니다.')}return r.json()}
async function refresh(){if(!props.user||props.user.consent_required||disposed)return;try{const result=await request('/api/analyses');if(disposed)return;rows.value=result;if(selected.value && selected.value.state!=='SUCCEEDED'){const row=rows.value.find(r=>r.id===selected.value.id);if(row){selected.value=row;if(row.state==='SUCCEEDED')await open(row)}}}catch(e){error.value=e.message}}
function stop(){startRevision++;starting.value=false;if(playing.value&&context)position.value=Math.min(duration.value,Math.max(0,context.currentTime-origin));playing.value=false;bufferedPlayer?.stop();for(const s of sources){try{s.source.stop()}catch{}s.source.disconnect();s.gain.disconnect()}sources=[];cancelAnimationFrame(raf)}
function clearMedia(){bufferedPlayer?.dispose();bufferedPlayer=null}
function createSource(t,buffer){const source=context.createBufferSource(),gain=context.createGain();source.buffer=buffer;source.connect(gain);gain.connect(masterNode);return{source,gain,family:t.family}}
function mix(){if(!context)return;masterNode.gain.setValueAtTime(master.value,context.currentTime);const levels=trackLevels(tracks.value,expandedGroups.value);for(const s of sources){s.gain.gain.setTargetAtTime(levels.get(s.family)||0,context.currentTime,.015)}}
function audioContext(){if(!context){context=new AudioContext();masterNode=context.createGain();masterNode.connect(context.destination)}return context}
async function open(row){
if(disposed)return;
expandedGroups.value={};
masterMemory={mute:[],solo:[]};stop();clearMedia();loadController?.abort();revision++;const token=revision;selected.value=row;page.value='library';tracks.value=[];position.value=0;buffers.clear();loaded.value=0;error.value='';loading.value=false;
windowed=(row.duration||0)>120;
if(row.state!=='SUCCEEDED')return;
loadController=new AbortController();const signal=loadController.signal;loading.value=true;loadStage.value='파형과 트랙 정보를 준비하고 있습니다';
try{
const detail=await request('/api/analyses/'+row.id,{signal});if(token!==revision)return;
await settled();if(token!==revision)return;
selected.value=detail;tracks.value=[...(detail.original_url?[{family:'original',url:detail.original_url,download:'/api/analyses/'+row.id+'/download/original',waveform:[],reference:true}]:[]),...detail.tracks].map(t=>({...t,mute:detail.kind==='part_comparison'||t.family==='original',solo:false,volume:1}));
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
function downloadChoice(track){window.location.href=track?track.download:selected.value.archive_url}
function tick(){if(!playing.value)return;position.value=Math.max(0,context.currentTime-origin);if(position.value>=duration.value){stop();position.value=0;if(loop.value)toggle();return}raf=requestAnimationFrame(tick)}
function seek(event){const was=playing.value||starting.value;stop();position.value=Math.min(duration.value,Math.max(0,Number(event.target.value)));if(was)toggle()}
function seekWave(event){const rect=event.currentTarget.getBoundingClientRect();const was=playing.value||starting.value;stop();position.value=(event.clientX-rect.left)/rect.width*duration.value;if(was)toggle()}
function choose(e){
if(uploading.value)return;
clearMetadata();fileDuration.value=null;readingFile.value=false;error.value='';rights.value=false;
file.value=e.target.files?.[0]||e.dataTransfer?.files?.[0]||null;
if(!file.value)return;
if(!/\.(mp3|wav|flac)$/i.test(file.value.name)){error.value='MP3, WAV, FLAC 파일을 선택해 주세요.';file.value=null;return}
if(file.value.size===0||file.value.size>1024**3){error.value='파일은 1GB 이하의 음원을 선택해 주세요.';file.value=null;return}
readingFile.value=true;const audio=new Audio();metadataAudio=audio;metadataUrl=URL.createObjectURL(file.value);audio.preload='metadata';
audio.onloadedmetadata=()=>{const length=audio.duration;readingFile.value=false;if(Number.isFinite(length)&&length>0){fileDuration.value=length;if(length>900){error.value='15분 이하의 음원을 선택해 주세요.';file.value=null;fileDuration.value=null}}clearMetadata()};
audio.onerror=()=>{readingFile.value=false;clearMetadata()};
metadataTimer=setTimeout(()=>{readingFile.value=false;clearMetadata()},10000);audio.src=metadataUrl;
}
const canDelete=row=>!!row&&!['QUEUED','RUNNING'].includes(row.state);
function askDelete(row,event){modalOrigin=originOf(event);deleteDialog.value={id:row.id,name:row.name}}
async function confirmDelete(){const d=deleteDialog.value;if(!d||deleting.value)return;deleting.value=true;error.value='';try{await request('/api/analyses/'+d.id,{method:'DELETE'});deleteDialog.value=null;if(selected.value?.id===d.id)home();await refresh()}catch(e){deleteDialog.value=null;error.value=e.message}finally{deleting.value=false}}
function newAnalysis(event){if(!props.user){emit('login',event);return}modalOrigin=originOf(event);modal.value=true;uploadStep.value=1;preset.value='';rights.value=false;file.value=null;fileDuration.value=null;readingFile.value=false;clearMetadata();error.value=''}
function goVersions(){if(!file.value||readingFile.value||uploading.value)return;if(rights.value)uploadStep.value=2;else rightsDialog.value=true}
function confirmRights(){rights.value=true;rightsDialog.value=false;uploadStep.value=2}
async function submit(){if(uploadStep.value===1){goVersions();return}if(!chosenVersion.value||!file.value||uploading.value)return;if(!rights.value){error.value='업로드한 음원의 이용 권한을 확인해 주세요.';return}if(!/\.(mp3|wav|flac)$/i.test(file.value.name)){error.value='MP3, WAV, FLAC 파일을 선택해 주세요.';return}uploading.value=true;uploadPercent.value=0;error.value='';try{const row=await new Promise((resolve,reject)=>{const xhr=new XMLHttpRequest();xhr.open('POST','/api/analyses?preset='+(releaseInfo.value?.presets?chosenVersion.value.commercial:preset.value)+'&rights='+encodeURIComponent(legalVersions.value?.copyright||''));xhr.setRequestHeader('X-Requested-With','MusicAnalyzer');xhr.setRequestHeader('X-Filename',encodeURIComponent(file.value.name));xhr.upload.onprogress=e=>{if(e.lengthComputable)uploadPercent.value=Math.round(e.loaded/e.total*100)};xhr.onload=()=>{if(xhr.status===401)window.dispatchEvent(new Event('music-session-expired'));try{const data=JSON.parse(xhr.responseText);xhr.status<300?resolve(data):reject(Error(data.error))}catch{reject(Error('업로드 응답을 확인할 수 없습니다.'))}};xhr.onerror=()=>reject(Error('서버에 연결하지 못했습니다.'));xhr.send(file.value)});modal.value=false;await refresh();await open(row)}catch(e){error.value=e.message}finally{uploading.value=false}}
function spaceKey(event){
if(event.key!==' '||!selected.value||modal.value||logoutDialog.value||withdrawDialog.value||deleteDialog.value||rightsDialog.value||event.ctrlKey||event.metaKey||event.altKey)return;
if(event.target.closest?.('input:not([type=range]),textarea,select,[contenteditable]'))return;
event.preventDefault();event.stopPropagation();
if(event.type==='keydown'&&!event.repeat&&!loading.value)toggle()}
onMounted(()=>{fetch('/api/legal').then(r=>r.json()).then(v=>{legalVersions.value=v}).catch(()=>{});fetch('/api/release').then(r=>r.json()).then(v=>{releaseInfo.value=v}).catch(()=>{});if(props.user&&!props.user.consent_required){refresh();timer=setInterval(refresh,1800);}window.addEventListener('resize',draw);window.addEventListener('keydown',spaceKey,true);window.addEventListener('keyup',spaceKey,true)});
onBeforeUnmount(()=>{clearMetadata();disposed=true;buffers.clear();loadController?.abort();revision++;stop();clearMedia();clearInterval(timer);window.removeEventListener('resize',draw);window.removeEventListener('keydown',spaceKey,true);window.removeEventListener('keyup',spaceKey,true);context?.close()});
</script>

<template>
<div class="studio" @pointerdown="press" :class="{'is-playing':playing}">
<aside class="sidebar"><a class="brand" href="#" @click.prevent="go('home',$event)"><span class="logo">≋</span><span>music<span class="brand-thin">analyzer</span><small>YOUR SOUND, UNLAYERED.</small></span></a><button class="button new-analysis" @click="newAnalysis($event)">＋ 새 분석</button><div class="workspace-label">MENU</div><button class="nav" :class="{active:page==='home'}" @click="go('home',$event)"><span>⌂</span>홈</button><button class="nav" :class="{active:page==='library'}" @click="go('library',$event)"><span>♫</span>라이브러리<b class="nav-count">{{completed}}</b></button></aside>
<main>
<header class="topbar"><nav class="crumbs" aria-label="현재 위치"><button class="crumb" @click="go('home',$event)">워크스페이스</button><span class="slash">/</span><template v-if="selected"><button class="crumb" @click="go('library',$event)">라이브러리</button><span class="slash">/</span><span>트랙 스튜디오</span></template><span v-else>{{page==='library'?'라이브러리':'홈'}}</span></nav><div class="top-right"><template v-if="user"><span class="account-name">{{user.display_name}}</span><button class="button small" :disabled="accountBusy" :aria-busy="accountBusy" @click="modalOrigin=originOf($event);logoutDialog=true">{{accountBusy?'로그아웃 중…':'로그아웃'}}</button><button class="link-button" :disabled="accountBusy" @click="modalOrigin=originOf($event);withdrawDialog=true">회원 탈퇴</button></template><button v-else data-account-login class="button small" @click="emit('login',$event)">로그인</button></div></header>
<div v-if="error&&!modal" role="alert" class="error">{{error}}<button @click="error=''">닫기</button></div>
<Transition :css="false" mode="out-in" @enter="pageEnter" @leave="pageLeave" @after-enter="draw"><section v-if="!selected" :key="page" class="home">
<template v-if="page==='library'">
<div class="page-heading"><span class="eyebrow">LIBRARY</span><h1>내 분석 라이브러리</h1><p>내 계정으로 분석한 곡과 분리된 트랙을 확인하세요.</p></div>
<div class="library-heading"><span class="lib-count">전체 <b>{{filtered.length}}</b>곡</span><label v-if="user" class="search"><span>⌕</span><input v-model="search" placeholder="곡 이름 검색" aria-label="곡 이름 검색"></label></div>
<div class="library"><div class="table-header"><span>곡 이름</span><span>분석 구성</span><span>길이</span><span>상태</span><span></span></div><div v-for="(row,i) in paged" :key="row.id" class="library-item"><button class="library-row" @click="visit(row,$event)"><div class="song-cell"><div class="song-icon" :style="{'--accent':['#b39bfa','#74c9b1','#8ab5e5','#dda778'][i%4]}">≋</div><div><strong>{{row.name}}</strong><small>{{row.track_count}} tracks <span>·</span> {{typeof row.created==='string'?row.created.slice(0,10):'이전 분석'}}</small></div></div><span class="model-label">{{modelName(row.model,row.separation_version)}}<em v-if="isBeta(row.model)" class="beta-chip">BETA</em></span><span class="duration">{{stamp(row.duration)}}</span><span class="badge" :class="row.state">{{stateName(row.state)}}<span v-if="row.state==='RUNNING'"> · {{row.progress}}%</span></span></button><button v-if="canDelete(row)" class="row-delete" :aria-label="row.name+' 분석 삭제'" @click="askDelete(row,$event)">삭제</button></div><div v-if="!filtered.length" class="empty"><template v-if="!user">로그인하면 내 분석 결과를 확인할 수 있습니다. <button class="button small" @click="emit('login',$event)">로그인하기</button></template><template v-else>{{search?'검색 결과가 없습니다.':'아직 분석한 곡이 없습니다. 첫 음원을 추가해 보세요.'}}</template></div></div>
<nav v-if="pageCount>1" class="pager" aria-label="페이지"><button :disabled="libPage<=1" @click="libPage=Math.max(1,libPage-1)" aria-label="이전 페이지">‹</button><template v-for="(p,k) in pageNums" :key="p"><span v-if="k&&p-pageNums[k-1]>1" class="gap">…</span><button :class="{active:p===Math.min(libPage,pageCount)}" :aria-current="p===Math.min(libPage,pageCount)?'page':null" @click="libPage=p">{{p}}</button></template><button :disabled="libPage>=pageCount" @click="libPage=Math.min(pageCount,libPage+1)" aria-label="다음 페이지">›</button></nav></template>
<template v-else>
<div class="page-heading"><span class="eyebrow">MUSIC ANALYZER</span><h1>음악을, <em>한 트랙씩.</em></h1><p>보컬만, 드럼만, 기타만. 듣고 싶은 소리만 골라 들을 수 있어요.</p></div>
<div class="hero"><div class="hero-copy"><h2>곡에서 소리를 분리하세요!</h2><p>음원 한 곡을 올리면 보컬, 드럼, 베이스, 기타까지 파트별로 나눠 줘요.<br>2·6·13트랙 중에 골라서 따로 듣고, 파일로 받아 갈 수 있어요.<br>13트랙은 현재 BETA(연구 중) 기능이에요.</p><button class="button white" @click="newAnalysis">＋ 새 분석 만들기 <span>↗</span></button><div class="hero-tags">MP3 · WAV · FLAC <span>최대 15분</span></div></div><div class="hero-art" aria-hidden="true"><div v-for="(color,i) in ['#c6b2ff','#72d5b5','#edaf72','#88b8ff','#e2c77f']" :key="color" class="art-track" :style="{'--tint':color,transform:'translateX('+(i%2?25:0)+'px)'}"><span class="art-dot"></span><div class="art-wave"><i v-for="n in 58" :key="n" :style="{height:(8+Math.abs(Math.sin(n*2.7+i)*Math.cos(n*.2+i))*35)+'px'}"></i></div></div><div class="art-playhead"></div><div class="art-badge">2 / 6 / 13 tracks · 13 BETA <span>◉</span></div></div></div>
<section class="lp about-lp"><div class="about-top"><div class="about-left"><span class="eyebrow">ABOUT</span><h2>음원에서 파트별 소리를 <em>따로 뽑아 주는 서비스</em></h2></div><div class="about-right"><div class="about-points"><article><h3>이런 서비스예요</h3><p>한 곡에 섞여 있는 보컬과 악기를 AI가 파트별로 나눠요.<br>결과는 트랙 하나하나가 따로 재생되는 오디오 파일이에요.</p></article><article><h3>이렇게 쓰여요</h3><p>보컬만 빼고 연습하거나, 베이스·기타 파트를 귀로 따거나<br>드럼만 들으며 편곡을 분석할 수 있어요.</p></article><article><h3>이런 점이 달라요</h3><p>2·6·13트랙 중에서 고를 수 있고,<br>여러 단계의 분석으로 트랙 간 혼입을 줄여요.</p></article></div>
</div></div><div class="about-flow"><div class="flow-in"><span class="flow-label">올린 음원</span><div class="lane" style="--tint:#c7ccd9"><span class="lane-dot"></span><b>원곡</b><div class="lane-wave"><i v-for="n in 160" :key="n" :style="{height:(8+Math.abs(Math.sin(n*1.3)*Math.cos(n*.21)+Math.sin(n*.7)*.5)*14)+'px'}"></i></div></div></div><span class="flow-arrow">→</span><div class="flow-out"><span class="flow-label">분리된 트랙</span><div v-for="(t,i) in [['보컬','vocals'],['드럼','drums'],['베이스','bass'],['기타','guitar'],['피아노','piano']]" :key="t[0]" class="lane" :style="{'--tint':colors[t[1]]}"><span class="lane-dot"></span><b>{{t[0]}}</b><div class="lane-wave"><i v-for="n in 160" :key="n" :style="{height:(5+Math.abs(Math.sin(n*1.9+i*2.3)*Math.cos(n*.37+i))*18)+'px'}"></i></div></div></div></div>
</section>
<section class="lp plans-lp"><div class="lp-head"><span class="eyebrow">TRACK PLANS</span><h2>용도에 따라 다르게 분리할 수 있어요</h2></div><div class="lp-body"><div class="plan-split"><div class="plan-side"><article v-for="c in compare.slice(0,2)" :key="c.id"><b>{{c.title}}</b><div><h3>{{c.lead}}</h3><p>{{c.text}}</p><div class="recommend"><ul><li v-for="f in c.fit.split(' · ')" :key="f">{{f}}</li></ul></div></div><div class="plan-lanes"><div v-for="(t,i) in c.tracks" :key="t[0]" class="lane" :style="{'--tint':colors[t[1]]||'#9a8bd0','--d':i*45+'ms'}"><span class="lane-dot"></span><b>{{t[0]}}</b><div class="lane-wave"><i v-for="n in 160" :key="n" :style="{height:(5+Math.abs(Math.sin(n*1.9+i*2.3)*Math.cos(n*.37+i))*18)+'px'}"></i></div></div></div></article></div>
<div class="plan-panel" v-for="c in compare.slice(2)" :key="c.id"><div class="plan-info"><b class="plan-big">{{c.title}}<em v-if="c.beta" class="beta-badge">BETA</em></b><h3>{{c.lead}}</h3><p>{{c.text}}</p><div class="recommend"><ul><li v-for="f in c.fit.split(' · ')" :key="f">{{f}}</li></ul></div></div><div class="plan-lanes"><div v-for="(t,i) in c.tracks" :key="t[0]" class="lane" :style="{'--tint':colors[t[1]]||'#9a8bd0','--d':i*45+'ms'}"><span class="lane-dot"></span><b>{{t[0]}}</b><div class="lane-wave"><i v-for="n in 160" :key="n" :style="{height:(5+Math.abs(Math.sin(n*1.9+i*2.3)*Math.cos(n*.37+i))*18)+'px'}"></i></div></div></div></div></div>
</div></section>
<section class="lp feature-lp"><div class="lp-head"><span class="eyebrow">STUDIO</span><h2>분리된 트랙을 스튜디오처럼 다뤄 보세요</h2></div><div class="lp-body"><div class="studio-split"><div class="studio-list"><div v-for="(f,i) in studioFeatures" :key="f[0]" class="studio-item"><span class="studio-num">0{{i+1}}</span><div class="studio-real" :style="{'--track':f[4]}"><div v-if="f[3]==='is-m'||f[3]==='is-s'" class="track-settings"><button :class="{selected:f[3]==='is-m'}">M</button><button :class="{selected:f[3]==='is-s'}">S</button></div><div v-else-if="f[3]==='is-v'" class="track-settings"><input type="range" min="0" max="2" step=".01" value="1" tabindex="-1" aria-hidden="true"><span>100%</span></div><div v-else-if="f[3]==='is-r'" class="master-left"><button class="partial">M</button><button class="partial">S</button></div><div v-else-if="f[3]==='is-u'" class="play-controls"><button class="reset enabled" tabindex="-1" aria-hidden="true">↻</button></div><div v-else-if="f[3]==='is-p'" class="play-controls"><button class="reset" tabindex="-1" aria-hidden="true">↤</button><button class="play" tabindex="-1" aria-hidden="true">▶</button></div><button v-else class="track-download" tabindex="-1" aria-hidden="true">↓</button></div><div><h3>{{f[1]}}</h3><p>{{f[2]}}</p></div></div></div><figure class="shot"><img src="/studio-tracks.png" alt="트랙 스튜디오 실제 화면" width="580" height="450" loading="lazy"></figure></div></div></section>

<section class="lp sample-lp"><div class="lp-head"><span class="eyebrow">SAMPLE</span><h2>Sample Track</h2></div><div class="lp-body"><SamplePlayer/></div></section>
<section class="lp faq-lp"><div class="lp-head"><span class="eyebrow">FAQ</span><h2>자주 묻는 질문</h2></div><div class="lp-body"><div class="faq-tabs" role="tablist"><button v-for="(g,i) in faq" :key="g.tab" role="tab" :aria-selected="faqTab===i" :class="{active:faqTab===i}" @click="faqTab=i;faqOpen=-1">{{g.tab}}</button></div><div class="faq-list" :key="faqTab"><div v-for="(item,i) in faq[faqTab].items" :key="item[0]" class="faq-item" :class="{open:faqOpen===i}" :style="{'--i':i}"><button class="faq-q" :aria-expanded="faqOpen===i" @click="faqOpen=faqOpen===i?-1:i"><span>{{item[0]}}</span><i aria-hidden="true">+</i></button><div class="faq-a"><div class="faq-a-in"><p>{{item[1]}}</p></div></div></div></div></div></section>
</template>
<SiteFooter />
</section>
<section v-else :key="selected.id" class="session">
<button class="back" @click="home">← 라이브러리로 돌아가기</button>
<div class="session-heading"><div><h1>{{selected.name}}<span v-if="isBeta(selected.model)" class="beta-badge" :title="betaResultNote" tabindex="0">BETA · 연구 중</span></h1><p v-if="isBeta(selected.model)" class="beta-note">{{betaResultNote}}</p><p>{{modelName(selected.model,selected.separation_version)}} <span>·</span> {{stamp(duration)}} <span>·</span> {{selected.track_count}} 트랙<template v-if="tracks.some(t=>t.reference)"> <span>+</span> 원본</template></p></div><div v-if="selected.archive_url||canDelete(selected)" class="session-actions"><template v-if="selected.archive_url"><button class="button" @click="downloadChoice(null)">↓ 전체 트랙 다운로드</button></template><button v-if="canDelete(selected)" class="button small danger" @click="askDelete(selected,$event)">분석 삭제</button></div></div>
<div v-if="selected.state!=='SUCCEEDED'" class="processing"><div v-if="selected.state!=='FAILED'" class="spinner"></div><div v-else class="failed-symbol">!</div><span class="tiny-label">ANALYSIS SESSION</span><h2>{{stageTitle}}</h2><p v-if="selected.state!=='FAILED'">{{versionFor(selected.model)?.note||'선택한 구성으로 음원을 분리합니다.'}}</p><p v-else>분석을 완료하지 못했습니다. 파일 형식과 길이를 확인한 뒤 다시 시도해 주세요. 이 분석은 삭제할 수 있습니다.</p><div class="progress-line"><i :style="{width:selected.progress+'%'}"></i></div><div class="progress-caption"><span>{{selected.total_chunks?((selected.completed_chunks||0)+' / '+selected.total_chunks+' 구간'):'현재 단계 준비 및 처리 중'}}</span><b>{{selected.progress}}%</b></div><div class="stage-steps"><template><span v-for="(item,i) in analysisSteps" :key="item.number" :class="{done:selected.progress>=item.end,current:selected.progress<item.end&&(i===0||selected.progress>=analysisSteps[i-1].end)}">{{item.number}} {{item.label}}</span></template></div></div>
<template v-else>
<div v-if="loading" class="track-loading" role="status" aria-live="polite" aria-busy="true">
<div class="spinner"></div><h2>트랙을 준비하고 있습니다</h2><p>{{loadStage}}</p>
<div class="progress-line"><i :style="{width:(tracks.length?loaded/tracks.length*100:0)+'%'}"></i></div>
<div class="progress-caption"><span>{{loaded}} / {{tracks.length||selected.track_count||'—'}} 트랙</span><b>{{tracks.length?Math.round(loaded/tracks.length*100):0}}%</b></div>
</div>
<div v-else-if="tracks.length&&loaded!==tracks.length" class="track-loading"><h2>트랙을 불러오지 못했습니다</h2><button class="button" @click="open(selected)">다시 불러오기</button></div>
<template v-else>
<div class="transport master-row"><div class="master-left"><span class="master-label">전체</span><button :class="{selected:allMuted,partial:anyMuted&&!allMuted}" @click="masterToggle('mute',anyMuted)" aria-label="전체 음소거" :aria-pressed="allMuted?'true':anyMuted?'mixed':'false'" :title="anyMuted?'눌려 있는 음소거를 모두 해제':'모든 트랙 음소거'">M</button><button :class="{selected:allSolo,partial:anySolo&&!allSolo}" @click="masterToggle('solo',anySolo)" aria-label="전체 솔로" :aria-pressed="allSolo?'true':anySolo?'mixed':'false'" :title="anySolo?'눌려 있는 솔로를 모두 해제':'모든 트랙 솔로'">S</button></div><div class="master-main"><div class="play-controls"><button class="reset" aria-label="처음으로" @click="stop();position=0">↤</button><button class="play" :disabled="loading" @click="toggle" :aria-label="starting?'재생 준비 취소':playing?'일시정지':'재생'">{{loading||starting?'◌':playing?'Ⅱ':'▶'}}</button><button class="reset" aria-label="모든 볼륨 기본값으로" title="모든 볼륨 기본값으로" @click="resetVolumes">↻</button><div class="time"><strong>{{stamp(position)}}</strong><span>/ {{stamp(duration)}}</span></div></div><div class="transport-right"><span v-if="loading" class="loading-text">트랙 불러오는 중 {{loaded}} / {{tracks.length}}</span><span class="rate">44.1 kHz <span>STEREO</span></span><label class="master">마스터<input v-model.number="master" type="range" min="0" max="2" step=".01" @input="mix" @dblclick="master=1;mix()" title="더블클릭하여 기본 음량(100%)으로 복원" aria-label="마스터 음량" :aria-valuetext="Math.round(master*100)+'%'"><span>{{Math.round(master*100)}}%</span></label></div></div><span></span></div>
<div class="daw" :aria-busy="starting" :class="{'daw-playing':playing,'daw-buffering':starting}"><div v-if="starting" class="track-buffer-overlay" role="status" aria-live="polite"><div class="track-buffer-card"><span class="buffer-spinner"></span><strong>재생 구간 준비 중…</strong><span>{{stamp(position)}} · 전체 트랙</span></div></div>
<div class="daw-ruler"><span>TRACKS <b>{{tracks.length}}</b></span><div class="ruler-scale"><i v-for="tick in rulerTicks" :key="tick.t" :style="{left:tick.left+'%'}">{{tick.t}}s</i><input class="timeline" type="range" :value="position" min="0" :max="duration" step=".1" @input="seek" aria-label="재생 위치"><div class="ruler-head" :style="{left:(position/duration*100)+'%'}"></div></div><span></span></div>
<div v-for="(track,i) in visibleTracks" :key="track.family" class="track-row" :style="{'--track':colors[track.family]||'#8da9d7','--index':i}" :class="{muted:track.mute,solo:track.solo}">
<div class="track-info"><div class="track-title"><span class="track-icon" aria-hidden="true"><Drum v-if="track.family==='drums'" :size="22" :stroke-width="1.8"/><svg v-else viewBox="0 0 24 24"><path :d="trackIcons[track.family]||mdiMusicNote"/></svg></span><b>{{trackTitle(track)}}</b><span class="track-format">{{track.reference?'REF':'WAV'}}</span></div><div class="track-settings"><button :class="{selected:track.mute}" @click="track.mute=!track.mute;mix()" :aria-label="trackTitle(track)+' 음소거'" :aria-pressed="track.mute">M</button><button :class="{selected:track.solo}" @click="track.solo=!track.solo;mix()" :aria-label="trackTitle(track)+' 솔로'" :aria-pressed="track.solo">S</button><input v-model.number="track.volume" type="range" min="0" max="2" step=".01" @input="mix" @dblclick="track.volume=1;mix()" title="더블클릭하여 기본 음량(100%)으로 복원" :aria-label="trackTitle(track)+' 음량'"><span>{{Math.round(track.volume*100)}}%</span></div></div>
<div class="waveform" @click="seekWave"><canvas :data-wave="track.family"></canvas><div class="playhead" :style="{left:(position/duration*100)+'%'}"></div></div><button class="track-download" @click="downloadChoice(track)" :aria-label="trackTitle(track)+' WAV 다운로드'">↓</button></div>
<div v-if="loading&&!tracks.length" class="empty">파형을 준비하고 있습니다…</div>
</div><div class="session-foot"><span>원본은 기본 음소거입니다. 원본의 S 버튼으로 분리 결과와 비교하세요.</span><span>다운로드는 44.1kHz FLOAT WAV · 음량 조절은 재생에만 적용</span></div>
</template></template><SiteFooter /></section></Transition>
</main>
<Transition :css="false" @enter="modalEnter" @leave="modalLeave"><div v-if="modal" class="modal-backdrop" @pointerdown="backdropDown=$event.target===$event.currentTarget" @click.self="backdropDown&&!uploading&&(modal=false)" @keydown.esc="!uploading&&(modal=false)">
<form class="modal analysis-modal" :class="{'has-version':uploadStep===2&&chosenVersion,'is-upload-step':uploadStep===1,'is-version-step':uploadStep===2}" role="dialog" aria-modal="true" aria-labelledby="modal-title" @submit.prevent="submit">
<div class="modal-top"><button type="button" class="close" @click="modal=false" :disabled="uploading" aria-label="닫기">×</button></div>
<nav class="upload-tabs" aria-label="새 분석 단계"><button type="button" :class="{active:uploadStep===1}" :disabled="uploading" @click="uploadStep=1">1. 파일 업로드</button><button type="button" :class="{active:uploadStep===2}" :disabled="!file||readingFile||uploading" @click="goVersions">2. 버전 선택</button></nav>
<h2 id="modal-title">{{uploadStep===1?'음원을 업로드하세요.':'어떤 트랙으로 추출할까요?'}}</h2>
<Transition name="analysis-tab" mode="out-in"><section v-if="uploadStep===1" key="upload" class="analysis-tab-panel"><p>음원을 선택한 다음 추출 버전을 골라 주세요.</p><label class="dropzone" @dragover.prevent @drop.prevent="choose"><input type="file" accept=".mp3,.wav,.flac" @change="choose" :disabled="uploading" aria-label="음원 파일 선택"><span class="upload-symbol">↥</span><strong>{{file?file.name:'음원을 드래그하거나 클릭해 선택'}}</strong><small>{{file?(file.size/1024/1024).toFixed(1)+' MB':'MP3, WAV, FLAC · 최대 1GB / 15분'}}</small></label><p class="modal-note" aria-live="polite">{{readingFile?'곡 길이를 확인하고 있습니다…':fileDuration?'곡 길이 '+stamp(fileDuration):file?'곡 길이를 읽지 못했습니다. 분석은 진행할 수 있습니다.':'파일을 선택하면 곡 길이를 확인합니다.'}}</p></section>
<section v-else key="versions" class="analysis-tab-panel"><div class="version-layout"><div class="version-selection"><p class="selected-file"><strong>{{file?.name}}</strong><span>{{fileDuration?'곡 길이 '+stamp(fileDuration):'곡 길이 확인 불가'}}</span></p><p v-if="!offered.length" class="modal-note" role="alert">현재 운영 환경에서 제공되는 분석 구성이 없습니다.</p><div class="version-options" role="radiogroup" aria-label="추출 버전"><label v-for="version in offered" :key="version.id" class="version-option" :class="{selected:preset===version.id}"><input type="radio" name="analysis-version" v-model="preset" :value="version.id"><span><strong>{{version.title}}<em v-if="version.beta" class="beta-badge">BETA</em><em v-if="version.badge" class="beta-tag">{{version.badge}}</em></strong><span>{{version.description}}</span><span class="version-estimate" v-if="versionEstimate(version.id)">예상 분석시간 · {{formatEstimate(versionEstimate(version.id).low)}} ~ {{formatEstimate(versionEstimate(version.id).high)}}<small>{{versionEstimate(version.id).basis}}</small></span><span class="version-estimate" v-else>예상 분석시간 · 곡 길이 확인 필요</span><small>{{version.note}}</small></span></label></div><p class="modal-note">예상시간은 참고 범위이며, 업로드·대기시간은 제외됩니다. 실제 처리시간은 달라질 수 있습니다.</p></div><Transition name="version-details"><aside v-if="chosenVersion" class="version-detail-panel" aria-live="polite"><Transition name="detail-content" mode="out-in"><div :key="chosenVersion.id"><span class="detail-eyebrow">분리 과정</span><h3>{{chosenVersion.title}} 분석<em v-if="chosenVersion.beta" class="beta-badge">BETA</em></h3><p>{{chosenVersion.note}}</p><p v-if="chosenVersion.beta" class="beta-notice" role="note">{{betaNotice}}</p><ol class="version-steps" tabindex="0" aria-label="분리 과정 목록"><li v-for="item in chosenVersion.steps" :key="item.number"><b>{{item.number}} {{item.label}}</b><span>{{item.text}}</span></li></ol></div></Transition></aside></Transition></div></section></Transition>
<div v-if="error" role="alert" class="error">{{error}}</div><div v-if="uploading" class="upload-state"><span>음원 올리기 중</span><b>{{uploadPercent}}%</b><div class="progress-line"><i :style="{width:uploadPercent+'%'}"></i></div></div><button class="button full" type="submit" :disabled="uploading||(uploadStep===1?(!file||readingFile):(!file||!chosenVersion||!rights))">{{uploading?'음원 올리기 중…':uploadStep===1?'다음 · 버전 선택':'분석 시작하기'}} <span>→</span></button></form>
</div></Transition>
<Transition :css="false" @enter="modalEnter" @leave="modalLeave"><div v-if="logoutDialog" class="modal-backdrop" @pointerdown="backdropDown=$event.target===$event.currentTarget" @click.self="backdropDown&&(logoutDialog=false)" @keydown.esc="logoutDialog=false"><div class="modal confirm-modal" role="alertdialog" aria-modal="true" aria-labelledby="logout-title"><h2 id="logout-title">로그아웃하시겠습니까?</h2><div class="confirm-actions"><button type="button" class="button small confirm-cancel" @click="logoutDialog=false">취소</button><button type="button" class="button small" @click="logoutDialog=false;emit('logout')">로그아웃</button></div></div></div></Transition>
<Transition :css="false" @enter="modalEnter" @leave="modalLeave"><div v-if="rightsDialog" class="modal-backdrop" @pointerdown="backdropDown=$event.target===$event.currentTarget" @click.self="backdropDown&&(rightsDialog=false)" @keydown.esc="rightsDialog=false"><div class="modal confirm-modal" role="alertdialog" aria-modal="true" aria-labelledby="rights-title" aria-describedby="rights-text"><h2 id="rights-title">업로드 콘텐츠 권리 확인</h2><p id="rights-text" class="confirm-text">본인은 업로드한 콘텐츠를 본 서비스를 통해 저장·분석·변환할 수 있는 권리 또는 적법한 이용 권한을 보유하고 있음을 확인합니다.<br><br>타인의 저작물을 이용하는 경우 필요한 권리와 허락 여부를 확인할 책임은 이용자에게 있습니다. 자세한 내용은 <a href="/copyright" target="_blank" rel="noopener">저작권 및 콘텐츠 정책</a>을 확인해 주세요.</p><div class="confirm-actions"><button type="button" class="button small confirm-cancel" @click="rightsDialog=false">취소</button><button type="button" class="button small" autofocus @click="confirmRights">확인</button></div></div></div></Transition><Transition :css="false" @enter="modalEnter" @leave="modalLeave"><div v-if="deleteDialog" class="modal-backdrop" @pointerdown="backdropDown=$event.target===$event.currentTarget" @click.self="backdropDown&&!deleting&&(deleteDialog=null)" @keydown.esc="!deleting&&(deleteDialog=null)"><div class="modal confirm-modal" role="alertdialog" aria-modal="true" aria-labelledby="delete-title" aria-describedby="delete-text"><h2 id="delete-title">분석을 삭제하시겠습니까?</h2><p id="delete-text" class="confirm-text"><b>{{deleteDialog.name}}</b><br>이 분석을 삭제하면 업로드한 음원과 생성된 분리 결과에 더 이상 접근할 수 없습니다. 삭제된 분석은 복구할 수 없습니다.</p><div class="confirm-actions"><button type="button" class="button small confirm-cancel" :disabled="deleting" @click="deleteDialog=null">취소</button><button type="button" class="button small danger" :disabled="deleting" @click="confirmDelete">{{deleting?'삭제 중…':'삭제'}}</button></div></div></div></Transition>
<Transition :css="false" @enter="modalEnter" @leave="modalLeave"><div v-if="withdrawDialog" class="modal-backdrop" @pointerdown="backdropDown=$event.target===$event.currentTarget" @click.self="backdropDown&&(withdrawDialog=false)" @keydown.esc="withdrawDialog=false"><div class="modal confirm-modal" role="alertdialog" aria-modal="true" aria-labelledby="withdraw-title" aria-describedby="withdraw-text"><h2 id="withdraw-title">회원 탈퇴</h2><p id="withdraw-text" class="confirm-text">회원 탈퇴 시 계정과 개인 분석 라이브러리가 삭제되며 복구할 수 없습니다.</p><div class="confirm-actions"><button type="button" class="button small confirm-cancel" @click="withdrawDialog=false">취소</button><button type="button" class="button small danger" @click="withdrawDialog=false;emit('withdraw')">회원 탈퇴</button></div></div></div></Transition>

</div>
</template>
