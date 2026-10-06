import {test} from 'node:test';
import assert from 'node:assert/strict';
import {trackLevels} from './src/trackGroups.js';
const fixture=()=>[{family:'vocals',volume:1,mute:false,solo:false},{family:'lead',parent_family:'vocals',volume:1,mute:false,solo:false},{family:'backing',parent_family:'vocals',volume:1,mute:false,solo:false},{family:'drums',volume:1,mute:false,solo:false}];
test('collapsed and expanded groups never double-play',()=>{let t=fixture();let x=trackLevels(t,{});assert.equal(x.get('vocals'),1);assert.equal(x.get('lead'),0);x=trackLevels(t,{vocals:true});assert.equal(x.get('vocals'),0);assert.equal(x.get('lead'),1);assert.equal(x.get('backing'),1)});
test('group mute and volume apply to both children',()=>{let t=fixture();t[0].volume=.4;let x=trackLevels(t,{vocals:true});assert.equal(x.get('lead'),.4);t[0].mute=true;x=trackLevels(t,{vocals:true});assert.equal(x.get('lead'),0);assert.equal(x.get('backing'),0)});
test('group solo selects children and excludes unrelated tracks',()=>{let t=fixture();t[0].solo=true;let x=trackLevels(t,{vocals:true});assert.equal(x.get('lead'),1);assert.equal(x.get('backing'),1);assert.equal(x.get('drums'),0)});
test('hidden child solo does not silence collapsed playback',()=>{let t=fixture();t[1].solo=true;let x=trackLevels(t,{});assert.equal(x.get('vocals'),1);assert.equal(x.get('drums'),1)});
