import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {defaultOrbit,orbitCamera,rotateOrbit,zoomOrbit,panOrbit,createCloudSession} from '../examples/interactive-cloud/cloud-view.mjs';
const scene=JSON.parse(readFileSync(new URL('../contracts/cloud-hero.json',import.meta.url),'utf8'));
test('canonical camera roundtrip, 360-degree orbit and bounded pitch/zoom',()=>{
  const o=defaultOrbit(scene),c=orbitCamera(o);
  assert.ok(c.eye.every((v,i)=>Math.abs(v-scene.camera.eye[i])<1e-10));
  const spin=rotateOrbit(o,Math.PI*2/.008,0);
  assert.ok(orbitCamera(spin).eye.every((v,i)=>Math.abs(v-c.eye[i])<1e-10));
  assert.ok(Math.abs(rotateOrbit(o,0,1e5).pitch)<=1.39);
  const z=zoomOrbit(o,-1e5,scene.extent);assert.ok(z.distance>=Math.max(...scene.extent)*.6);
  const p=panOrbit(o,20,10,scene.extent,300,40);assert.notDeepEqual(p.target,o.target);assert.deepEqual(o.target,scene.camera.target);
});
test('actual cloud field renders different views without rebuilding its optical cache',()=>{
  const session=createCloudSession(scene),o=defaultOrbit(scene);
  const a=session.render({orbit:o,interactive:true}),b=session.render({orbit:rotateOrbit(o,90,20),interactive:true});
  assert.equal(a.rgba.length,240*150*4);assert.ok(a.visible>100);assert.ok(b.visible>100);
  assert.notDeepEqual(a.rgba,b.rgba);assert.equal(a.fieldBuilds,1);assert.equal(b.fieldBuilds,1);assert.equal(b.cacheBuilds,1);assert.equal(b.reused,true);
  const c=session.render({orbit:o,interactive:true,light:'back'});assert.equal(c.fieldBuilds,1);assert.equal(c.cacheBuilds,2);assert.notDeepEqual(a.rgba,c.rgba);
  const d=session.render({orbit:o,interactive:true,light:'original'});assert.deepEqual(d.rgba,a.rgba);
});
