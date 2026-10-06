<script setup>
import {ref,onMounted,onBeforeUnmount,nextTick} from 'vue';
import App from './App.vue';
import {originOf,expand,collapse,press} from './motion';
const user=ref(null),ready=ref(false),busy=ref(false),error=ref('');
const email=ref(''),password=ref(''),displayName=ref(''),reveal=ref(false),generation=ref(0);
const errorBox=ref(null),showAuth=ref(false),mode=ref('login'),closing=ref(false);
let modalOrigin=null,opener=null,previousOverflow='',disposed=false;
const reduced=()=>matchMedia('(prefers-reduced-motion: reduce)').matches;
function login(event){
  if(showAuth.value||closing.value)return;
  modalOrigin=originOf(event);opener=event?.currentTarget||document.activeElement;
  mode.value='login';error.value='';password.value='';reveal.value=false;
  previousOverflow=document.body.style.overflow;document.body.style.overflow='hidden';showAuth.value=true;
}
function close(){if(busy.value||!showAuth.value)return;closing.value=true;showAuth.value=false;password.value='';reveal.value=false;error.value=''}
function switchMode(){if(busy.value)return;mode.value=mode.value==='login'?'register':'login';password.value='';reveal.value=false;error.value=''}
function enter(el,done){
  el.inert=true;
  el.animate([{opacity:0},{opacity:1}],{duration:reduced()?0:420,easing:'cubic-bezier(.22,.75,.18,1)'});
  expand(el.querySelector('.account-card'),modalOrigin,()=>{el.inert=false;done()});
}
function leave(el,done){
  el.inert=true;
  const opacity=getComputedStyle(el).opacity;
  for(const animation of el.getAnimations())animation.cancel();
  el.animate([{opacity},{opacity:0}],{duration:reduced()?0:380,easing:'cubic-bezier(.22,.75,.18,1)',fill:'forwards'});
  collapse(el.querySelector('.account-card'),modalOrigin,done);
}
function focusModal(el){el.querySelector('input:not(:disabled)')?.focus({preventScroll:true})}
function afterLeave(){
  closing.value=false;document.body.style.overflow=previousOverflow;
  nextTick(()=>{
    const target=opener?.isConnected?opener:document.querySelector('[data-account-login]')||document.querySelector('.account-workspace h1');
    if(target){if(target.tagName==='H1')target.tabIndex=-1;target.focus({preventScroll:true})}
    opener=null;modalOrigin=null;
  });
}
function modalKeydown(event){
  keyboardPress(event);
  if(event.key==='Escape'){event.preventDefault();event.stopPropagation();close();return}
  if(event.key!=='Tab')return;
  const controls=[...event.currentTarget.querySelectorAll('button:not(:disabled),input:not(:disabled),[tabindex="0"]')];
  if(!controls.length){event.preventDefault();return}
  const first=controls[0],last=controls.at(-1),active=document.activeElement;
  if(event.shiftKey&&(active===first||!controls.includes(active))){event.preventDefault();last.focus()}
  else if(!event.shiftKey&&(active===last||!controls.includes(active))){event.preventDefault();first.focus()}
}
function contentEnter(el,done){expand(el,null,done)}
function contentLeave(el,done){el.inert=true;collapse(el,null,done)}
function keyboardPress(event){if(!event.repeat&&['Enter',' '].includes(event.key)&&event.target.closest('button'))press(event)}
async function showError(message){error.value=message;await nextTick();errorBox.value?.focus({preventScroll:true})}
async function authRequest(path,data){
  const response=await fetch('/api/auth/'+path,data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Requested-With':'MusicAnalyzer'},body:JSON.stringify(data)});
  const result=await response.json();
  if(!response.ok){const failure=new Error(result.error||'요청을 처리하지 못했습니다.');failure.status=response.status;throw failure}
  return result;
}
async function submit(event){
  if(busy.value)return;
  const submittedMode=mode.value;
  busy.value=true;error.value='';
  try{
    const result=await authRequest(mode.value,{email:email.value,password:password.value,display_name:displayName.value});
    if(disposed)return;
    user.value=result.user;password.value='';reveal.value=false;generation.value++;
    closing.value=true;showAuth.value=false;
  }catch(e){if(!disposed&&mode.value===submittedMode)await showError(e.message)}
  finally{busy.value=false}
}
async function logout(){
  if(busy.value)return;
  busy.value=true;error.value='';
  try{await authRequest('logout',{});if(disposed)return;user.value=null;password.value='';generation.value++;error.value=''}
  catch(e){if(!disposed)await showError(e.message)}finally{busy.value=false}
}
function expired(){user.value=null;generation.value++;login();error.value='로그인이 만료되었습니다. 다시 로그인해 주세요.'}
onMounted(async()=>{
  window.addEventListener('music-session-expired',expired);
  const legacyAuth=['#login','#register'].includes(window.location.hash)?window.location.hash.slice(1):null;
  if(legacyAuth)history.replaceState(null,'',location.pathname+location.search);
  try{user.value=(await authRequest('me')).user}catch(e){if(e.status!==401)error.value=e.message}
  finally{ready.value=true;if(legacyAuth&&!user.value){login();mode.value=legacyAuth}}
});
onBeforeUnmount(()=>{disposed=true;if(showAuth.value||closing.value)document.body.style.overflow=previousOverflow;window.removeEventListener('music-session-expired',expired)});
</script>

<template>
  <div v-if="!ready" class="account-screen account-loading" role="status"><span class="account-spinner" aria-hidden="true"></span>스튜디오를 준비하고 있습니다…</div>
  <template v-else>
    <div class="account-workspace" :inert="showAuth||closing" @keydown="keyboardPress">
      <Transition name="account-feedback"><div v-if="error&&!showAuth&&!closing" ref="errorBox" tabindex="-1" class="error" role="alert">{{error}}<button @pointerdown="press" @click="error=''">닫기</button></div></Transition>
      <App :key="(user?.id||'guest')+generation" :user="user" :account-busy="busy" @logout="logout" @login="login" />
    </div>
    <Teleport to="body">
    <Transition :css="false" @enter="enter" @leave="leave" @after-enter="focusModal" @after-leave="afterLeave">
    <div v-if="showAuth" class="modal-backdrop account-backdrop" @click.self="close" @pointerdown="press" @keydown="modalKeydown">
      <form class="account-card" role="dialog" aria-modal="true" :aria-busy="busy" aria-labelledby="account-title" @submit.prevent="submit">
        <div class="account-modal-top"><span class="tiny-label">{{mode==='register'?'CREATE ACCOUNT':'YOUR WORKSPACE'}}</span><button class="close" type="button" aria-label="로그인 창 닫기" :disabled="busy" @click="close">×</button></div>
        <Transition :css="false" mode="out-in" @enter="contentEnter" @leave="contentLeave" @after-enter="focusModal">
        <div :key="mode" class="account-content">
        <div class="eyebrow">MUSIC ANALYZER</div>
        <h2 id="account-title">{{mode==='register'?'나만의 스튜디오 만들기':'다시 만나 반가워요.'}}</h2>
        <p>내 음원을 분석하고 나만의 라이브러리에서 이어서 들어보세요.</p>
        <label v-if="mode==='register'" class="account-field">이름<input v-model="displayName" autocomplete="name" required maxlength="80" :disabled="busy"></label>
        <label class="account-field">이메일<input v-model="email" type="email" autocomplete="username" required maxlength="254" :disabled="busy"></label>
        <div class="account-field">
          <label for="account-password">비밀번호</label>
          <div class="password-control"><input id="account-password" v-model="password" :type="reveal?'text':'password'" :autocomplete="mode==='register'?'new-password':'current-password'" required minlength="10" maxlength="128" :disabled="busy" :aria-describedby="mode==='register'?'password-help':undefined"><button class="password-reveal" type="button" :disabled="busy" :aria-pressed="reveal" :aria-label="reveal?'비밀번호 숨기기':'비밀번호 보기'" @click="reveal=!reveal">{{reveal?'숨기기':'보기'}}</button></div>
          <small v-if="mode==='register'" id="password-help">10~128자로 입력해 주세요.</small>
        </div>
        <Transition name="account-feedback"><div v-if="error" ref="errorBox" tabindex="-1" class="error" role="alert"><span>{{error}}</span><button type="button" aria-label="오류 메시지 닫기" @click="error=''">닫기</button></div></Transition>
        <button class="button full" :disabled="busy"><span v-if="busy" class="account-spinner" aria-hidden="true"></span><span aria-live="polite">{{busy?'잠시만 기다려 주세요…':mode==='register'?'회원가입':'로그인'}}</span><span v-if="!busy" class="account-submit-arrow" aria-hidden="true">→</span></button>
        <button class="account-switch" type="button" :disabled="busy" @click="switchMode">{{mode==='login'?'처음 오셨나요? 회원가입':'이미 계정이 있나요? 로그인'}}</button>
        </div></Transition>
      </form>
    </div>
    </Transition>
    </Teleport>
  </template>
</template>

<style scoped>
.account-workspace{min-height:100vh;transform-origin:center}
.account-screen{margin:0;width:100%;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:32px;background:#0d0e12;color:#e5e6ec;overflow:hidden}
.account-loading{gap:12px;font-size:13px;color:#aaa2b8}
.account-backdrop{z-index:120;padding:24px;overflow-y:auto;overscroll-behavior:contain}
.account-modal-top{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}.account-modal-top .close{line-height:1;padding:4px 7px}.account-modal-top .close:hover:not(:disabled){color:#ded3ff;background:#292536;border-radius:5px}
.account-card{max-height:calc(100dvh - 48px);overflow-y:auto;width:min(460px,100%);padding:clamp(24px,4vw,40px);border:1px solid #2c2e39;border-radius:20px;background:#15161d;box-shadow:0 18px 70px #0002;transform-origin:center}
.account-back{display:inline-flex;gap:7px;align-items:center;background:none;padding:6px 0;margin-bottom:18px;color:#aaa2b8;font-size:12px}
.account-back span,.account-submit-arrow{display:inline-block;transition:transform .3s cubic-bezier(.22,.75,.18,1)}
.account-back:hover:not(:disabled){color:#d8caff}.account-back:hover:not(:disabled) span{transform:translateX(-4px)}
h2{font-size:27px;letter-spacing:-1px;margin:16px 0}p{font-size:14px;line-height:1.7;color:#9992a4;margin-bottom:28px}
.account-field{display:flex;flex-direction:column;gap:8px;margin-bottom:20px;font-size:13px;font-weight:600;transition:color .22s}.account-field:focus-within{color:#c6b5ff}
input{width:100%;box-sizing:border-box;padding:13px 14px;border:1px solid #353342;border-radius:9px;font:inherit;background:#111218;color:#e5e6ec}
input:hover:not(:disabled){border-color:#66557f}input:focus{outline:1px solid #a793fa;outline-offset:0;border-color:#a793fa;box-shadow:0 0 0 3px #b6a2ff12}
input:disabled{opacity:.55}input:user-invalid{border-color:#e499ab}small{font-weight:400;color:#aaa2b8}
.password-control{position:relative}.password-control input{padding-right:72px}.password-reveal{position:absolute;right:8px;top:50%;margin-top:-15px;padding:7px 9px;border-radius:5px;background:transparent;color:#aaa2b8;font-size:11px;line-height:16px}.password-reveal:hover:not(:disabled){background:#292536;color:#d8caff}
.account-switch{display:block;margin:22px auto 0;padding:8px;border:0;border-radius:6px;background:none;color:#b6a2ff;cursor:pointer}.account-switch:hover:not(:disabled){background:#292536;color:#d8caff;box-shadow:0 0 18px #b6a2ff12}
.account-card .error{display:flex;align-items:center;gap:12px;justify-content:space-between;margin:12px 0;font-size:13px}.error button{flex-shrink:0}.error:focus{outline:1px solid #e499ab;outline-offset:3px}
.account-card .button.full{justify-content:center;gap:10px;min-height:44px}.button.full:hover:not(:disabled) .account-submit-arrow{transform:translateX(4px)}.button:disabled{box-shadow:none;filter:none}
.account-spinner{width:16px;height:16px;display:inline-block;flex-shrink:0;border:2px solid currentColor;border-right-color:transparent;border-radius:50%;animation:account-spin .8s linear infinite}
@keyframes account-spin{to{transform:rotate(360deg)}}
.account-feedback-enter-active,.account-feedback-leave-active{transition:opacity .2s,transform .2s}.account-feedback-enter-from,.account-feedback-leave-to{opacity:0;transform:translateY(-6px)}
@media(max-width:480px){.account-screen{padding:20px}.account-card{padding:24px}h2{font-size:23px}}
@media(prefers-reduced-motion:reduce){.account-spinner{animation:none}.account-back span,.account-submit-arrow,.account-field,.account-feedback-enter-active,.account-feedback-leave-active{transition:none}.account-back:hover span,.button.full:hover .account-submit-arrow{transform:none}}
</style>
