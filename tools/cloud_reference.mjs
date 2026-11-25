/** Canonical v0.13 cloud scene; Float32 fields and opaque sRGB frame. Independent JS, never Rust evidence. */
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {generateFidelityVolume,prepareFidelityVolume} from '../bindings/web/fidelity.mjs';
const [profile,out]=process.argv.slice(2);
const scene=JSON.parse(await readFile(new URL('../contracts/cloud-hero.json',import.meta.url),'utf8'));
const spec=scene.profiles[profile];if(!spec||!out)throw Error('usage: node tools/cloud_reference.mjs preview|hero OUTPUT');
await mkdir(out,{recursive:true});const t=performance.now();
const volume=generateFidelityVolume(scene.preset,{quality:scene.quality,cells:spec.cells,extent:scene.extent,settings:scene.settings,time:scene.time});
const gen=performance.now()-t,start=performance.now();
const r=prepareFidelityVolume({...volume,material:scene.material,...scene.lighting});const prepare=performance.now()-start;
const rt=performance.now(),f=r.render({...scene.camera,width:spec.width,height:spec.height,steps:spec.steps});const render=performance.now()-rt;
const files={};async function put(name,b){await writeFile(join(out,name),b);files[name]={bytes:b.length,sha256:createHash('sha256').update(b).digest('hex')};}
function f32(a){const b=Buffer.alloc(a.length*4);for(let i=0;i<a.length;i++)b.writeFloatLE(a[i],4*i);return b;}
await put('density.f32',f32(volume.fields.density));await put('temperature.f32',f32(volume.fields.temperature));await put('alpha.f32',f32(f.alpha));await put('frame.rgba',Buffer.from(f.rgba));
await writeFile(join(out,'reference.json'),JSON.stringify({schema:'vapor.cloud-reference/1',source:'actual-js-reference',profile,cells:volume.cells,extent:volume.extent,densityCap:volume.densityCap,width:spec.width,height:spec.height,files,generationMs:gen,prepareMs:prepare,renderMs:render,visiblePixels:f.diagnostics.visiblePixels},null,2)+'\n');
console.log('JS reference rendered',profile,gen,prepare,render);
