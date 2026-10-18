// SPDX-License-Identifier: GPL-3.0-only
const assert = require('node:assert/strict');
const M = require('../Model.js');

let state = M.initial();
for (let i=0;i<=36;i++) state=M.reduce(state,M.fixture(i),i*400);
assert.equal(state.result,true);
assert.equal(state.phase,'complete');
assert.equal(state.download,250);
assert.equal(state.upload,115);
assert.equal(M.mbps(-1),null);
assert.equal(M.mbps(Infinity),null);
assert.equal(M.mbps('5'),null);
assert.equal(M.reduce(state,{type:'download',download:{bandwidth:1}},20000).download,250);
assert.ok(M.reduce(M.initial(),{type:'result'},0).error);
assert.equal(M.reduce(M.initial(),{type:'download',download:{bandwidth:0}}).download,0);
for (let bits=0;bits<8;bits++) assert.equal(M.canFinish(!!(bits&1),!!(bits&2),!!(bits&4)),bits===7);
console.log('Model: event lifecycle, Mbps, final results and completion ordering passed.');
