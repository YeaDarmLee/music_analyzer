import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {versions,compare,isBeta,betaNotice,defaultSteps,versionFor} from './src/versions.js';
import {docs} from './src/legalDocs.js';

const app=readFileSync(new URL('./src/App.vue',import.meta.url),'utf8');
const flat=doc=>JSON.stringify(doc);

test('only the 13-track version is marked BETA, everywhere it is described',()=>{
  assert.deepEqual(versions.filter(v=>v.beta).map(v=>v.id),['final_11']);
  assert.deepEqual(compare.filter(v=>v.beta).map(v=>v.id),['final_11']);
  assert.ok(isBeta('final_11')&&isBeta('commercial_13'));
  for(const id of ['basic_2','basic_6','final_10'])assert.equal(isBeta(id),false);
  const thirteen=versions.find(v=>v.id==='final_11');
  assert.match(thirteen.description,/실험적 분석 기능/);
  assert.match(thirteen.note,/결과 편차가 클 수 있습니다/);
  assert.match(betaNotice,/연구 및 개선 중인 기능/);
});

test('BETA markers are wired into the home, selection, result, library and FAQ views',()=>{
  assert.match(app,/v-if="version\.beta"[^>]*>BETA</);
  assert.match(app,/BETA · 연구 중/);
  assert.match(app,/c\.beta/);
  assert.match(app,/isBeta\(row\.model\)/);
  assert.match(app,/13트랙은 2트랙이나 6트랙보다 더 정확한가요\?/);
});

test('user-facing steps are the five outcome-level stages and hide internals',()=>{
  assert.deepEqual(defaultSteps.map(s=>s.label),['음원 준비','기본 파트 분리','세부 악기 분석','품질 보정','결과 검증']);
  const data=JSON.stringify([versions,compare,defaultSteps]);
  for(const word of ['Mega','evidence','STFT','phase','threshold','RULES','STRENGTH','원곡 악기 근거','심벌','source→target','잔차 계산','엉뚱한 트랙'])
    assert.ok(!data.includes(word),'internal detail exposed: '+word);
  for(const word of ['Mega','STFT','원곡 악기 근거','심벌','엉뚱한 트랙','원곡을 함께 살펴'])
    assert.ok(!app.includes(word),'internal detail exposed in App.vue: '+word);
  assert.ok(!app.includes('{{selected.stage}}')&&!app.includes('{{selected.error}}'),'server stage/error text must not be shown verbatim');
  assert.ok(!versions.find(v=>v.id==='basic_2').steps.some(s=>s.label==='세부 악기 분석'));
});

test('marketing copy follows the practice/analysis positioning',()=>{
  for(const phrase of ['DAW와 동일','다른게 분리','오케스트라 까지','노래방 MR','파트별 커버','정밀 분석','가장 자세히','바로잡아요'])
    assert.ok(!(JSON.stringify([versions,compare])+app).includes(phrase),'old copy remains: '+phrase);
  for(const phrase of ['분리된 트랙을 스튜디오처럼 다뤄 보세요','용도에 따라 다르게 분리할 수 있어요','풀밴드부터 오케스트라까지','여러 단계의 분석으로 트랙 간 혼입을 줄여요'])
    assert.ok((JSON.stringify([versions,compare])+app).includes(phrase),'new copy missing: '+phrase);
});

test('legal pages exist with placeholders instead of invented operator details',()=>{
  assert.deepEqual(Object.keys(docs),['terms','privacy','copyright']);
  assert.equal(docs.terms.sections.length,16);
  assert.match(flat(docs.terms),/\[운영자명\]/);
  assert.match(flat(docs.privacy),/\[문의 이메일\]/);
  assert.match(flat(docs.copyright),/\[저작권 신고 이메일\]/);
  for(const doc of Object.values(docs)){
    const text=flat(doc);
    assert.doesNotMatch(text,/@[a-z0-9-]+\.[a-z]{2,}/i,'no concrete email address');
    assert.doesNotMatch(text,/100% 합법|저작권 문제 없|제102조|면제됩니다\./);
  }
});

test('privacy policy states the implemented retention and no AI training',()=>{
  const text=flat(docs.privacy);
  assert.match(text,/최대 7일/);
  assert.match(text,/15분/);
  assert.match(text,/AI 모델 학습 또는 학습 데이터셋 구축에 사용하지 않습니다/);
  assert.match(text,/비밀번호 원문은 저장하지 않습니다/);
  assert.doesNotMatch(text,/암호화 저장|암호화하여 저장/);
  assert.doesNotMatch(text,/항상 Secure/);
  assert.doesNotMatch(text,/이전 버전/,'no archive of old versions exists');
  assert.match(text,/임시 파일은 분석 준비가 완료되거나 실패하면 삭제/);
});

test('legacy members get a consent gate and signup/gate share the consent fields',()=>{
  const gate=readFileSync(new URL('./src/AccountGate.vue',import.meta.url),'utf8');
  assert.match(gate,/user\?\.consent_required/);
  assert.match(gate,/acceptPolicies/);
  assert.equal(gate.match(/<ConsentFields/g).length,2);
});

test('fonts are self-hosted: no third-party font host is referenced',()=>{
  for(const file of ['./src/style.css','./src/fonts.css','./index.html','./src/legalDocs.js']){
    const text=readFileSync(new URL(file,import.meta.url),'utf8');
    assert.doesNotMatch(text,/googleapis|gstatic|Google Fonts/,file);
  }
});

test('minimum age 14 is stated in terms, privacy policy and the signup form',()=>{
  assert.match(flat(docs.terms),/만 14세 이상 이용자를 대상으로/);
  assert.match(flat(docs.privacy),/만 14세 미만 아동을 대상으로 회원가입 서비스를 제공하지 않으며/);
  const fields=readFileSync(new URL('./src/ConsentFields.vue',import.meta.url),'utf8');
  assert.match(fields,/\[필수\]<\/b> 만 14세 이상입니다/);
  const gate=readFileSync(new URL('./src/AccountGate.vue',import.meta.url),'utf8');
  assert.equal(gate.match(/AGE14/g).length,2);
});

test('privacy rights list withdrawal of consent, suspension and objection',()=>{
  const text=flat(docs.privacy);
  for(const phrase of ['처리정지 및 동의 철회','이의를 제기할 수 있습니다','[문의 이메일]'])assert.ok(text.includes(phrase),phrase);
  const summary=readFileSync(new URL('./src/ConsentFields.vue',import.meta.url),'utf8');
  assert.match(summary,/비밀번호\(단방향 해시값으로 변환하여 저장\)/);
  assert.match(summary,/접속 IP의 해시값/);
});

test('every version maps to a commercial runtime preset and the UI sends the mapped id in commercial mode',()=>{
  assert.deepEqual(versions.map(v=>v.commercial),['commercial_2','commercial_6','commercial_13']);
  assert.equal(versionFor('commercial_13').id,'final_11');
  assert.equal(versionFor('final_11').id,'final_11');
  assert.ok(isBeta('commercial_13')&&!isBeta('commercial_6'));
  assert.match(app,/releaseInfo\.value\.presets\.includes\(v\.commercial\)/);
  assert.match(app,/releaseInfo\.value\?\.presets\?chosenVersion\.value\.commercial:preset\.value/);
});

test('user-facing screens do not name internal models or claim the download is the original file',()=>{
  const surface=readFileSync(new URL('./src/App.vue',import.meta.url),'utf8');
  for(const word of ['RoFormer','Demucs','CLAPSep','AudioSep','Mega53','원본 FLOAT WAV'])assert.ok(!surface.includes(word),word);
  assert.match(surface,/44\.1kHz FLOAT WAV/);
  assert.ok(!surface.includes('side-legal'),'legal links live in the footer only');
});

test('footer with legal links is rendered on the home page and on the track studio screen',()=>{
  assert.equal(app.match(/<SiteFooter \/>/g).length,2);
});

test('login does not leave a focused heading; sliders have no native focus box; sample mirrors studio mixer behaviour',()=>{
  const gate=readFileSync(new URL('./src/AccountGate.vue',import.meta.url),'utf8');
  assert.ok(!gate.includes("account-workspace h1"),'no heading focus fallback after login');
  const css=readFileSync(new URL('./src/style.css',import.meta.url),'utf8');
  assert.match(css,/\.track-settings input\[type=range\]:focus\s*,[^{]*\{\s*outline: none/);
  const sample=readFileSync(new URL('./src/SamplePlayer.vue',import.meta.url),'utf8');
  for(const feature of ['solo:solo[r.key]',"'daw-playing':playing","'is-playing':playing",'masterMemory','setTargetAtTime','resetFrame','aria-pressed'])
    assert.ok(sample.includes(feature),'sample player lacks '+feature);
});
