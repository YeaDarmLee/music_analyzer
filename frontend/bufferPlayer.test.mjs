import test from 'node:test';
import assert from 'node:assert/strict';
import {BufferedPlayer} from './src/bufferPlayer.js';
function fixture(overrides={}){
 const scheduled=[];const player=new BufferedPlayer({context:{currentTime:0,resume:async()=>{}},tracks:[{family:'a'},{family:'b'}],duration:90,fetchWindow:async(t,index)=>({index}),createChain:(t,buffer)=>({source:{start:(when,offset)=>scheduled.push([when,offset]),stop(){},disconnect(){}},gain:{disconnect(){}},filters:[],family:t.family}),onSources(){},onError:e=>{throw e},...overrides});return{player,scheduled};
}
test('current and next windows share sample-clock start times',async()=>{const{player,scheduled}=fixture();assert.equal(await player.start(5),true);await player.window(1);await Promise.resolve();assert.deepEqual(scheduled,[[.08,5],[.08,5],[25.08,0],[25.08,0]]);player.dispose()});
test('stopping while resume is pending prevents delayed start',async()=>{let resume;const{player,scheduled}=fixture({context:{currentTime:0,resume:()=>new Promise(r=>resume=r)}});await player.prepare();const pending=player.start(0);for(let i=0;i<5;i++)await Promise.resolve();player.stop();resume();assert.equal(await pending,false);assert.equal(scheduled.length,0);player.dispose()});
test('far seek evicts previous windows',async()=>{const{player}=fixture();await player.prepare();await player.window(1);await player.start(65);assert.deepEqual([...player.cache.keys()],[2]);player.dispose();assert.equal(player.cache.size,0)});
