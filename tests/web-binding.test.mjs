// Executes a C/WASM ABI test double. Not validation of Rust or fluid numerics.
import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs/promises';
import {loadVapor,VaporError} from '../bindings/web/vapor.mjs';
const path=process.env.VAPOR_TEST_FIXTURE_WASM;if(!path)throw Error('Set VAPOR_TEST_FIXTURE_WASM; no fake pass on missing fixture');
const module=await loadVapor(await fs.readFile(path));
function sim(options={}){return module.createSimulation({cells:[4,5,6],...options});}
test('config layout and validation',()=>{const s=sim({cellSize:.125,origin:[1,2,3]});try{assert.deepEqual(s.config.cells,[4,5,6]);assert.equal(s.config.cellSize,.125);assert.deepEqual(s.config.origin,[1,2,3]);assert.throws(()=>sim({cells:[-1,4,4]}),RangeError);assert.throws(()=>sim({bogus:1}),TypeError);}finally{s.dispose();}});
test('emitter/obstacle and metrics layout',()=>{const s=sim();try{s.setEmitter(0,{position:[1.25,2.5,3.75],densityRate:7.5,speed:.5});s.setSphere(0,[0,0,0],.25);const m=s.metrics();assert.deepEqual(m.centroid,[1.25,2.5,3.75]);assert.equal(m.maxDensity,7.5);assert.equal(m.pressureResidualRms,.25);assert.equal(m.cpuBytes,1234567);assert.equal(m.clampedVelocities,17);}finally{s.dispose();}});
test('advance, reset, and error statuses',()=>{const s=sim();try{s.step(3);assert.equal(s.advance(.1).alpha,.25);assert.equal(s.metrics().ticks,4);s.reset();assert.equal(s.metrics().ticks,0);assert.throws(()=>s.step(601),VaporError);assert.throws(()=>s.advance(NaN),TypeError);}finally{s.dispose();}});
test('field snapshots and memory growth',()=>{const s=sim();try{const a=s.field();assert.equal(a.length,120);assert.equal(a[98],1);const before=module.e.memory.buffer;const p=module.alloc(2*1024*1024);assert.notEqual(module.e.memory.buffer,before);module.free(p);const b=s.field();b[0]=77;assert.equal(a[0],0);assert.equal(s.field('velocity').length,360);assert.equal(s.field('velocity')[1],1.5);}finally{s.dispose();}});
test('atlas and profile contracts',()=>{const s=sim();try{const a=s.atlasRGBA8();assert.equal(a.length,480);assert.deepEqual([...a.slice(4,8)],[1,9,3,255]);s.setProfile(0,[[0,1,0,1],[1,1,1,1]],{repeat:true});s.setProfile(0,null);assert.throws(()=>s.setProfile(0,[[0,1]]),TypeError);}finally{s.dispose();}});
test('dispose idempotent and stale handle blocked',()=>{const s=sim();s.field();s.dispose();s.dispose();assert.ok(s.closed);assert.throws(()=>s.step(),VaporError);});
test('prototype-named fields are rejected before the native boundary',()=>{const s=sim();try{for(const name of ['toString','constructor','__proto__'])assert.throws(()=>s.field(name),TypeError);}finally{s.dispose();}});
test('disposal attempts every cached free even when one free reports failure',()=>{const s=sim();s.field();s.atlasRGBA8();s.macCells();const original=module.free;let frees=0;module.free=function(p){frees++;original.call(this,p);if(frees===1)throw new Error('deliberate free failure');};try{assert.throws(()=>s.dispose(),/deliberate free failure/);assert.equal(frees,3);assert.ok(s.closed);s.dispose();assert.equal(frees,3);}finally{module.free=original;}});
test('CPU preview calls real ABI shape and returns owned snapshots (C fixture only)',()=>{
 const s=sim();try{
  const a=s.renderRGBA8({eye:[1,1,1],target:[0,0,0],width:12,height:8,steps:16});
  assert.equal(a.length,12*8*4);assert.ok(a.every(x=>x===0));
  const before=a.buffer;const block=module.alloc(2*1024*1024);module.free(block);
  const b=s.renderRGBA8({eye:[1,1,1],target:[0,0,0],width:12,height:8,steps:16});
  assert.notEqual(b.buffer,before);b[0]=42;assert.equal(a[0],0);
 }finally{s.dispose();}
});
test('CPU preview rejects excessive work, missing camera and unknown options',()=>{
 const s=sim();try{
  assert.throws(()=>s.renderRGBA8({eye:[1,1,1],target:[0,0,0],width:4096,height:4096,steps:1024}),RangeError);
  assert.throws(()=>s.renderRGBA8({}),TypeError);
  assert.throws(()=>s.renderRGBA8({eye:[1,1,1],target:[0,0,0],bogus:1}),TypeError);
  assert.throws(()=>s.renderRGBA8({eye:[NaN,1,1],target:[0,0,0]}),TypeError);
 }finally{s.dispose();}
 assert.throws(()=>s.renderRGBA8({eye:[1,1,1],target:[0,0,0]}),VaporError);
});

import {NativeFidelityCPU} from '../bindings/web/native-fidelity.mjs';
test('native Fidelity WASM fixture: generation layouts, terrain, and owned output',()=>{
 const sdk=new NativeFidelityCPU(module),f=sdk.generate('ground_fog',{cells:[4,5,6],extent:[2,3,4],settings:{seed:5,coverage:.25,wind:[0,0,2]},time:.5,terrain:new Float32Array(24).fill(.25)});
 assert.equal(f.model,'rust-wasm-fidelity');assert.equal(f.fields.density.length,120);assert.equal(f.fields.density[0],2.75);assert.equal(f.fields.temperature[0],27.25);const dust=sdk.generate('dust',{cells:[4,4,4],settings:{seed:0,wind:[0,0,0]}});assert.equal(dust.fields.temperature[0],30);
 const before=f.fields.density.buffer,block=module.alloc(2*1024*1024);module.free(block);assert.equal(f.fields.density[0],2.75);assert.notEqual(before,module.e.memory.buffer);
});
test('native Fidelity WASM fixture: render layouts and scene data',()=>{
 const sdk=new NativeFidelityCPU(module),v={cells:[4,4,4],extent:[2,3,4],densityCap:8,fields:{density:new Float32Array(64).fill(2),temperature:new Float32Array(64).fill(3)}};
 const frame=sdk.render(v,{eye:[1,2,3],target:[0,0,0],width:8,height:4,steps:32,scene:{depth:new Float32Array(32).fill(6),radiance:new Float32Array(96).fill(.5)}},{shadowSteps:12,extinction:.5});
 assert.deepEqual([...frame.rgba.slice(0,4)],[12,32,6,255]);assert.equal(frame.alpha[0],7);assert.equal(frame.rgba.length,128);
});
test('native Fidelity rejects malformed inputs and old binaries without fallback',()=>{
 const sdk=new NativeFidelityCPU(module);assert.throws(()=>sdk.generate('steam'),RangeError);assert.throws(()=>sdk.generate('cumulus_cloud',{cells:[512,512,512]}),RangeError);assert.throws(()=>sdk.generate('ground_fog',{cells:[4,4,4],terrain:new Float32Array(1)}),RangeError);assert.throws(()=>sdk.generate('ground_fog',{settings:{oops:1}}),TypeError);
 const old=new (module.constructor)({...module.e,vapor_fidelity_generate_v1:undefined});assert.throws(()=>new NativeFidelityCPU(old),/exports missing/);
});
