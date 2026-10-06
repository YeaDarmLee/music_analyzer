import {strict as assert} from 'node:assert';
import {estimateAnalysis,formatEstimate,timingProfile} from './analysisEstimate.js';

assert.equal(estimateAnalysis(null,'basic_2'),null);
assert.equal(estimateAnalysis(Infinity,'basic_2'),null);
const initial=estimateAnalysis(180,'basic_2');
assert.ok(initial.low<initial.high);
assert.ok(estimateAnalysis(180,'final_11').low>initial.low);
const rows=[
  {state:'SUCCEEDED',model:'basic_2',timing_profile:timingProfile,duration:180,processing_seconds:60},
  {state:'SUCCEEDED',model:'basic_2',timing_profile:'old',duration:180,processing_seconds:900},
  {state:'FAILED',model:'basic_2',timing_profile:timingProfile,duration:180,processing_seconds:900},
];
assert.deepEqual(estimateAnalysis(180,'basic_2',rows),{low:35,high:85,basis:'최근 분석 기준'});
assert.equal(formatEstimate(45),'45초');
assert.equal(formatEstimate(120),'2분');
assert.equal(formatEstimate(125),'2분 5초');
console.log('Analysis estimate checks passed.');
