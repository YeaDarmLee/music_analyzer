// User-facing description of the analysis versions. Progress thresholds are the only link to the
// worker; labels and texts deliberately describe outcomes, not the internal processing order.
export const BETA_MODELS=['final_11','commercial_13'];
export const isBeta=id=>BETA_MODELS.includes(id);
// A version keeps its UI id; `commercial` is the runtime preset served (and sent) when the server runs the commercial release profile.
export const versionFor=model=>versions.find(v=>v.id===model||v.commercial===model);

const prepare=['01','음원 준비',5,'업로드한 오디오를 분석에 적합한 형식으로 준비합니다.'];
const base=['02','기본 파트 분리',50,'보컬과 주요 악기 파트를 분석합니다.'];
const detail=['03','세부 악기 분석',84,'선택한 구성에 따라 추가 악기 파트를 분석합니다.'];
const refine=['04','품질 보정',97,'트랙 간 혼입을 줄이고 결과를 정리합니다.'];
const verify=['05','결과 검증',100,'트랙의 길이와 오디오 결과를 확인한 뒤 저장합니다.'];
const step=([number,label,end,text])=>({number,label,end,text});

export const defaultSteps=[prepare,base,detail,refine,verify].map(step);

export const betaNotice='13트랙 분석은 현재 연구 및 개선 중인 기능입니다. 세부 악기의 음색이 비슷하거나 원곡에서 음량이 작은 경우 다른 트랙에 섞이거나 일부가 누락될 수 있습니다. 중요한 작업에 사용하기 전 결과를 직접 확인해 주세요.';
export const betaResultNote='세부 악기 분리는 실험 기능으로 결과가 곡마다 다를 수 있습니다.';

export const versions=[
{id:'basic_2',commercial:'commercial_2',title:'2트랙',description:'보컬 + 전체 반주',note:'메인보컬과 코러스를 함께 유지합니다.',steps:[prepare,[...base.slice(0,2),32,base[3]],verify].map(step)},
{id:'basic_6',commercial:'commercial_6',title:'6트랙',description:'보컬 · 기타 · 베이스 · 드럼 · 피아노 · 추가 반주',note:'기타는 통기타와 일렉을 구분하지 않습니다.\n신디·스트링·브라스는 별도 추출하지 않습니다.',steps:[prepare,[...base.slice(0,2),32,base[3]],detail,verify].map(step)},
{id:'final_11',commercial:'commercial_13',title:'13트랙',beta:true,badge:'실험 기능',description:'보컬·코러스와 세부 악기까지 나누는 실험적 분석 기능입니다. 음원에 따라 일부 악기의 오분류, 누락 또는 다른 트랙으로의 혼입이 발생할 수 있습니다.',note:'2·6트랙보다 처리 시간이 길고 결과 편차가 클 수 있습니다.',steps:defaultSteps}
];

export const compare=[
{id:'basic_2',title:'2트랙',lead:'보컬과 반주',tracks:[['보컬','vocals'],['전체 반주','instrumental']],text:'가장 빨리 끝나요. 코러스는 보컬에 같이 들어 있어요.',fit:'보컬 연습 · 반주 청취 · 곡 구조 파악'},
{id:'basic_6',title:'6트랙',lead:'밴드 구성 분리',tracks:[['보컬','vocals'],['기타','guitar'],['베이스','bass'],['드럼','drums'],['피아노','piano'],['추가 반주','other']],text:'기타는 통기타·일렉 구분 없이 하나로 나오고, 신디·스트링·브라스는 추가 반주에 들어 있어요.',fit:'밴드 연습 · 파트 카피 · 악기별 청취'},
{id:'final_11',title:'13트랙',beta:true,lead:'풀밴드부터 오케스트라까지',tracks:[['보컬','lead'],['코러스','backing'],['피아노','piano'],['신디사이저','synth'],['스트링','strings'],['브라스','brass'],['통기타','acoustic_guitar'],['일렉기타','guitar'],['베이스','bass'],['드럼','drums'],['추가 반주','other'],['기타 보조','guitar_residual'],['기타 타악기','percussion']],text:'보컬·코러스부터 신디, 스트링, 브라스, 기타까지 세부 악기로 나누는 실험 기능이에요. 곡에 따라 일부 악기가 다른 트랙에 섞이거나 누락될 수 있어요.',fit:'편곡 분석 · 세부 악기 청취 · 실험적 분석'}
];
