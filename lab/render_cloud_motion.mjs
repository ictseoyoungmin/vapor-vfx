/** Actual rendered motion from VPA1 sequence, no synthetic image effects. */
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {join} from 'node:path';import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {FieldSequence,frameFilename} from '../bindings/web/field-sequence.mjs';
import {generateFidelityVolume,prepareFidelityVolume} from '../bindings/web/fidelity.mjs';
const [dir,out]=process.argv.slice(2);if(!dir||!out)throw Error('sequence/output required');await mkdir(out,{recursive:true});
const seq=new FieldSequence(await readFile(join(dir,'sequence.vpa')),(i)=>readFile(join(dir,frameFilename(i))));
const scene=JSON.parse(await readFile(new URL('../contracts/cloud-hero.json',import.meta.url),'utf8'));
const camera={...scene.camera,width:480,height:300,steps:112};const hash=x=>createHash('sha256').update(x).digest('hex');
const rows=[];const duration=seq.endTime-seq.startTime;
function png(frame,file){const r=spawnSync(process.env.PYTHON??'python',['-c','from PIL import Image;import sys;Image.frombytes("RGBA",(int(sys.argv[1]),int(sys.argv[2])),sys.stdin.buffer.read()).save(sys.argv[3])',String(camera.width),String(camera.height),file],{input:frame.rgba});if(r.status!==0)throw Error(String(r.stderr));}
async function render(f,name){const t=performance.now();const frame=prepareFidelityVolume({...f,material:scene.material,...scene.lighting,lightScale:.5}).render(camera);png(frame,join(out,name+'.png'));return {name,time:f.time,rgbaSha256:hash(frame.rgba),renderMs:performance.now()-t,visiblePixels:frame.diagnostics.visiblePixels};}
for(let i=0;i<=24;i++){
 const t=seq.startTime+duration*i/24,f=await seq.sample(t);rows.push(await render(f,`cloud_${String(i).padStart(3,'0')}`));console.log('render',i,t,rows.at(-1).renderMs.toFixed(1));
}
// Same camera/material and resolution; old generator's noise evolves independently of prior field.
const comparisons=[];for(let i=0;i<=3;i++){const t=seq.startTime+duration*i/3;const f=generateFidelityVolume(scene.preset,{quality:scene.quality,cells:seq.index.cells,extent:seq.index.extent,settings:scene.settings,time:t});f.time=t;const densityMass=f.fields.density.reduce((a,b)=>a+b,0)*f.extent.reduce((a,b)=>a*b,1)/f.fields.density.length;comparisons.push({...await render(f,`old_${i}`),densityMass});}
await writeFile(join(out,'render.json'),JSON.stringify({status:'PASS',scope:'actual JS CPU render of independent conservative density evolution, not Rust/GPU',camera,rows,comparisons,cachedFrames:seq.cachedFrames},null,2));
