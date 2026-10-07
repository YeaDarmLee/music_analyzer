<script setup>
const terms=defineModel('terms',{default:false}),privacy=defineModel('privacy',{default:false});
defineProps({disabled:{type:Boolean,default:false}});
</script>

<template>
<fieldset class="consent-box">
  <legend class="sr-only">약관 동의</legend>
  <div class="consent-row"><label><input v-model="terms" type="checkbox" :disabled="disabled"><span><b>[필수]</b> 이용약관에 동의합니다.</span></label><a href="/terms" target="_blank" rel="noopener">내용 보기</a></div>
  <div class="consent-row"><label><input v-model="privacy" type="checkbox" :disabled="disabled"><span><b>[필수]</b> 개인정보 수집·이용에 동의합니다.</span></label><a href="/privacy" target="_blank" rel="noopener">내용 보기</a></div>
  <details class="consent-summary"><summary>개인정보 수집·이용 요약</summary>
    <dl>
      <dt>수집 목적</dt><dd>회원 식별 및 로그인 · 개인 분석 라이브러리 제공 · 서비스 보안 및 부정 이용 방지</dd>
      <dt>수집 항목</dt><dd>이메일, 닉네임, 비밀번호의 단방향 해시값, 로그인/세션 정보</dd>
      <dt>보유 기간</dt><dd>회원 탈퇴 시까지. 단, 법령상 별도의 보존 의무가 있는 경우 해당 기간</dd>
      <dt>동의 거부</dt><dd>개인정보 수집·이용에 동의하지 않을 수 있으나, 필수 정보 수집에 동의하지 않으면 회원 서비스 이용이 어렵습니다.</dd>
    </dl>
  </details>
</fieldset>
</template>

<style scoped>
.consent-box{margin:0 0 18px;padding:0;border:0;display:flex;flex-direction:column;gap:10px;font-size:13px;min-width:0}
.consent-row{display:flex;align-items:center;justify-content:space-between;gap:12px}
.consent-row label{display:flex;align-items:center;gap:9px;cursor:pointer;color:#d6d7e0;flex:1}
.consent-row input{width:18px;height:18px;padding:0;margin:0;flex-shrink:0;accent-color:#a793fa}
.consent-row b{color:#c6b5ff;font-weight:600}
.consent-row a{flex-shrink:0;color:#b6a2ff;font-size:12px}
.consent-summary{border:1px solid #2c2e39;border-radius:9px;padding:9px 12px;color:#aaa2b8;font-size:12px}
.consent-summary summary{cursor:pointer;color:#c6b5ff}
.consent-summary dl{margin:8px 0 0}.consent-summary dt{margin-top:8px;color:#d6d7e0;font-weight:600}.consent-summary dd{margin:2px 0 0;line-height:1.6}
.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}
</style>
