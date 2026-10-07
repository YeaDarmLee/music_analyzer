<script setup>
import {ref,computed,onMounted} from 'vue';
import SiteFooter from './SiteFooter.vue';
import {docs,EFFECTIVE} from './legalDocs';
const props=defineProps({page:{type:String,required:true}});
const doc=computed(()=>docs[props.page]);
const isLicenses=props.page==='licenses';
const title=isLicenses?'오픈소스 및 제3자 소프트웨어 고지':doc.value.title;
document.title=title+' · Music Analyzer';
const versions=ref({}),notices=ref({server:[],web:[]}),models=ref([]),failed=ref(false);
const tocItems=computed(()=>isLicenses?[['web','웹 화면에 포함된 구성요소'],['server','서버에서 사용하는 구성요소'],['models','모델 가중치']]:doc.value.sections.map(s=>[s.id,s.title]));
onMounted(async()=>{
  try{versions.value=await (await fetch('/api/legal')).json()}catch{}
  if(isLicenses){
    try{notices.value=await (await fetch('/licenses/components.json')).json();models.value=await (await fetch('/licenses/models.json')).json()}catch{failed.value=true}
  }
  if(location.hash)document.getElementById(location.hash.slice(1))?.scrollIntoView();
});
</script>

<template>
<div class="legal">
<header class="legal-top"><a class="legal-brand" href="/"><span aria-hidden="true">≋</span> music<span>analyzer</span></a><a class="legal-home" href="/">← 서비스로 돌아가기</a></header>
<main class="legal-body">
<h1>{{title}}</h1>
<p class="legal-meta" v-if="!isLicenses">정책 버전: {{versions[doc.version]||'—'}} · 시행일: {{EFFECTIVE}}</p>
<template v-if="isLicenses">
<p class="legal-lead">Music Analyzer는 여러 오픈소스 소프트웨어와 제3자 기술을 사용합니다. 각 구성요소의 저작권과 라이선스는 해당 권리자에게 있으며, Music Analyzer의 자체 소스 코드 및 독자적인 분석·라우팅·후처리 기술이 오픈소스로 공개된다는 의미는 아닙니다.</p>
<nav class="legal-toc" aria-label="목차"><a v-for="[id,label] in tocItems" :key="id" :href="'#'+id">{{label}}</a></nav>
<p v-if="failed" class="legal-note" role="alert">고지 목록을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.</p>
<section v-for="[id,label,rows] in [['web','웹 화면에 포함된 구성요소',notices.web],['server','서버에서 사용하는 구성요소',notices.server]]" :id="id" :key="id">
<h2>{{label}}</h2>
<div class="legal-table-wrap"><table><thead><tr><th>Component</th><th>Version</th><th>Copyright / Author</th><th>License</th><th>Official Project</th><th>License Text</th></tr></thead>
<tbody><tr v-for="row in rows" :key="row.name"><td>{{row.name}}</td><td>{{row.version}}</td><td>{{row.copyright}}</td><td>{{row.license}}</td><td><a :href="row.url" target="_blank" rel="noopener noreferrer">링크</a></td><td><a :href="row.text" target="_blank" rel="noopener noreferrer">보기</a></td></tr></tbody></table></div>
</section>
<p class="legal-lead">위 표에는 직접 사용하는 구성요소만 실었습니다. 이들이 다시 의존하는 하위 패키지는 각각의 라이선스를 따릅니다.</p>
<section id="models">
<h2>모델 가중치</h2>
<p v-if="!models.length">상용 공개 구성이 확정되면 그 구성이 실제로 사용하는 모델 가중치의 라이선스 근거가 이곳에 표시됩니다. 현재 확정되어 표시할 항목이 없습니다.</p>
<p v-else>아래는 상용 공개 구성이 실제로 사용하는 모델 가중치이며, 저작자가 선언한 라이선스를 근거 링크에서 확인할 수 있습니다. 저작자의 선언을 그대로 옮긴 것으로, 학습에 사용된 데이터의 권리나 특정 용도의 적법성을 보증하는 것은 아닙니다.</p>
<div v-if="models.length" class="legal-table-wrap"><table><thead><tr><th>Component</th><th>Author</th><th>License</th><th>Official Project</th><th>근거</th></tr></thead>
<tbody><tr v-for="m in models" :key="m.name"><td>{{m.name}}</td><td>{{m.author}}</td><td>{{m.license}}</td><td><a :href="m.url" target="_blank" rel="noopener noreferrer">링크</a></td><td><a :href="m.evidence" target="_blank" rel="noopener noreferrer">보기</a></td></tr></tbody></table></div>
</section>
</template>
<template v-else>
<p v-for="text in doc.intro" :key="text" class="legal-lead">{{text}}</p>
<nav class="legal-toc" aria-label="목차"><a v-for="[id,label] in tocItems" :key="id" :href="'#'+id">{{label}}</a></nav>
<section v-for="s in doc.sections" :id="s.id" :key="s.id">
<h2>{{s.title}}</h2>
<template v-for="(block,i) in s.body" :key="i">
<ul v-if="Array.isArray(block)"><li v-for="item in block" :key="item">{{item}}</li></ul>
<p v-else-if="typeof block==='object'"><a :href="block.link">{{block.text}}</a></p>
<p v-else>{{block}}</p>
</template>
</section>
</template>
<SiteFooter />
</main>
</div>
</template>

<style scoped>
.legal{min-height:100vh;background:#0d0e12;color:#e5e6ec;padding:0 16px}
.legal-top{display:flex;justify-content:space-between;align-items:center;max-width:900px;margin:0 auto;padding:22px 0;border-bottom:1px solid #23252f}
.legal-brand{color:#e5e6ec;text-decoration:none;font-weight:700;font-size:15px}.legal-brand span:last-child{font-weight:400;opacity:.7}.legal-brand span[aria-hidden]{color:#af8fff;margin-right:4px}
.legal-home{color:#aaa2b8;font-size:12px;text-decoration:none}.legal-home:hover{color:#d8caff}
.legal-body{max-width:860px;margin:0 auto;padding:40px 0 24px;line-height:1.8}
h1{font-size:28px;letter-spacing:-.8px;margin:0 0 10px}
.legal-meta{color:#8a8d9c;font-size:12px;margin:0 0 24px}
.legal-lead{color:#b7b9c6;font-size:14px;margin:0 0 20px}
.legal-toc{display:flex;flex-wrap:wrap;gap:6px 14px;padding:16px 18px;margin:0 0 32px;border:1px solid #23252f;border-radius:12px;background:#13141a;font-size:12px}
.legal-toc a{color:#b6a2ff;text-decoration:none}.legal-toc a:hover{text-decoration:underline}
section{scroll-margin-top:16px;margin-bottom:30px}
h2{font-size:17px;margin:0 0 10px;color:#f1f1f6}
p,li{font-size:14px;color:#c4c6d2;margin:0 0 10px;word-break:keep-all;overflow-wrap:anywhere}
ul{margin:0 0 12px;padding-left:20px}
a{color:#b6a2ff}
.legal-note{color:#f5b3c4}
.legal-table-wrap{overflow-x:auto;border:1px solid #23252f;border-radius:10px}
table{border-collapse:collapse;width:100%;min-width:720px;font-size:12px}
th,td{padding:10px 12px;border-bottom:1px solid #23252f;text-align:left;vertical-align:top;color:#c4c6d2}
th{color:#8a8d9c;font-weight:600;background:#13141a;white-space:nowrap}
tr:last-child td{border-bottom:0}
@media(max-width:600px){h1{font-size:23px}.legal-top{padding:16px 0}.legal-body{padding-top:28px}}
</style>
