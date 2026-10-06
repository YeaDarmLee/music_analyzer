export const timingProfile='staged-v8-overlap40';

export function estimateAnalysis(duration,model,rows=[]){
  if(!Number.isFinite(duration)||duration<=0)return null;
  const samples=rows.filter(r=>r.state==='SUCCEEDED'&&r.model===model&&r.timing_profile===timingProfile&&r.duration>=10&&r.processing_seconds>0)
    .map(r=>r.processing_seconds/r.duration).sort((a,b)=>a-b);
  const middle=Math.floor(samples.length/2);
  const rate=samples.length?(samples[middle]+samples[Math.floor((samples.length-1)/2)])/2:
    ({basic_2:15.56/10,basic_6:32.12/10,final_11:4*32.12/10}[model]);
  if(!rate)return null;
  return {low:Math.max(5,Math.floor(duration*rate*.6/5)*5),high:Math.max(10,Math.ceil(duration*rate*1.4/5)*5),
    basis:samples.length?'최근 분석 기준':model==='final_11'?'단계 수 기반 초기 추정':'기존 측정 기반 초기 추정'};
}

export function formatEstimate(seconds){
  return seconds<60?`${seconds}초`:`${Math.floor(seconds/60)}분${seconds%60?` ${seconds%60}초`:''}`;
}
