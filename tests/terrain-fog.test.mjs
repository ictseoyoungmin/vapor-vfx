import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createTerrainFogSession} from '../examples/high-fidelity/fog-view.mjs';
import {generateFidelityVolume,getFidelityPreset,prepareFidelityVolume} from '../bindings/web/fidelity.mjs';
import {valleyTerrain,createValleyScene} from '../examples/high-fidelity/valley.mjs';

test('default fog retains original Lab rendering and reuses optics for changed camera',()=>{
  const width=120,height=75,session=createTerrainFogSession();
  const a=session.render({width,height});
  const cells=[48,12,48],extent=[60,15,60],camera={eye:[29.8,6.5,-6],target:[30,3.9,34],fov:47,width,height};
  const style=getFidelityPreset('ground_fog','medium');
  style.material.extinction=.10;style.material.anisotropy=.25;
  const light={direction:[-.80,.56,.16],radiance:[.95,.80,.62]};
  const v=generateFidelityVolume('ground_fog',{cells,extent,terrain:valleyTerrain(cells,extent),settings:{coverage:.42,humidity:.64}});
  const opaque=createValleyScene(camera,light.direction);
  const old=prepareFidelityVolume({...v,material:style.material,...style.lighting,light,sunVisibility:opaque.sunVisibility,shadowSteps:32,lightScale:.5}).render({...camera,steps:96,scene:opaque.scene});
  assert.deepEqual(a.rgba,old.rgba);assert.ok(a.visiblePixels>100);
  const b=session.render({width,height,view:'oblique'});
  assert.notDeepEqual(b.rgba,a.rgba);assert.equal(b.fieldBuilds,1);assert.equal(b.cacheBuilds,1);assert.equal(b.reused,true);
  const c=session.render({width,height,lighting:'back'});
  assert.notDeepEqual(c.rgba,a.rgba);assert.equal(c.fieldBuilds,1);assert.equal(c.cacheBuilds,2);
  const d=session.render({width,height,coverage:.8});
  assert.notDeepEqual(d.rgba,a.rgba);assert.equal(d.fieldBuilds,2);assert.equal(d.reused,false);
  const e=session.render({width,height});assert.deepEqual(e.rgba,a.rgba);
});
