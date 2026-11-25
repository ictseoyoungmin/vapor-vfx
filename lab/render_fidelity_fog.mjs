import {writeFile,mkdir} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {generateFidelityVolume,prepareFidelityVolume,getFidelityPreset} from '../bindings/web/fidelity.mjs';
import {valleyTerrain,createValleyScene} from '../examples/high-fidelity/valley.mjs';
const dir=new URL('../reports/local/lab/fidelity/',import.meta.url),cells=[96,24,96],extent=[60,15,60],terrain=valleyTerrain(cells,extent),camera={width:800,height:500,eye:[29.8,6.5,-6],target:[30,3.9,34],fov:47,steps:160,exposure:1.0},light={direction:[.60,.34,.72],radiance:[.95,.80,.62]};
await mkdir(dir,{recursive:true});
const valley=createValleyScene(camera,light.direction),v=generateFidelityVolume('ground_fog',{cells,extent,terrain,settings:{coverage:.42,humidity:.64}}),material={...getFidelityPreset('ground_fog').material,extinction:.10,anisotropy:.25,ambient:.08,colour:[.89,.91,.96]},options={cells,extent,densityCap:1,material,light,sky:[.07,.105,.16],ground:[.015,.020,.018],multiScatter:.13,sunVisibility:valley.sunVisibility,shadowSteps:32,lightScale:.5};
const hash=a=>createHash('sha256').update(Buffer.from(a.buffer,a.byteOffset,a.byteLength)).digest('hex'),rows=[];
for(const [name,fields] of [['fog-valley',v.fields],['fog-valley-clear',{density:new Float32Array(v.fields.density.length),temperature:new Float32Array(v.fields.density.length)}]]){const start=performance.now(),p=prepareFidelityVolume({...options,fields}),img=p.render({...camera,scene:valley.scene});await writeFile(new URL(name+'.rgba',dir),img.rgba);rows.push({name,width:camera.width,height:camera.height,fieldSha256:hash(fields.density),rgbaSha256:hash(img.rgba),diagnostics:img.diagnostics,prepareAndRenderMs:performance.now()-start});console.log(name,rows.at(-1).prepareAndRenderMs);}
await writeFile(new URL('fog-comparison.json',dir),JSON.stringify({status:'PASS',source:'Actual analytic CPU scene, not a game screenshot',camera,cells,extent,material,light,trees:valley.trees,rows},null,2)+'\n');
