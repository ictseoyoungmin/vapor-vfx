/** Internal actual-WASM runner. Entry: validate_wasm_fidelity.py checks build receipt. */
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {loadVapor} from '../bindings/web/vapor.mjs';
import {NativeFidelityCPU} from '../bindings/web/native-fidelity.mjs';
const wasm=process.argv[2];if(!wasm)throw Error('Rust WASM path required');
const dir=new URL('../fixtures/fidelity-port/',import.meta.url),manifest=JSON.parse(await readFile(new URL('manifest.json',dir)));
const raw=async name=>{const file=manifest.files.find(f=>f.file===name);if(!file)throw Error('missing fixture declaration '+name);const b=await readFile(new URL(name,dir));if(b.length!==file.bytes||createHash('sha256').update(b).digest('hex')!==file.sha256)throw Error('fixture hash mismatch '+name);return b;};
const floats=async name=>{const b=await raw(name),a=new Float32Array(b.length/4);for(let i=0;i<a.length;i++)a[i]=b.readFloatLE(i*4);return a;};
function check(a,b,atol,rtol,label){if(a.length!==b.length)throw Error(label+' size mismatch');let max=0;for(let i=0;i<a.length;i++){const x=Math.abs(a[i]-b[i]);if(!Number.isFinite(x)||x>atol+rtol*Math.abs(b[i]))throw Error(`${label} at ${i}: ${a[i]} vs ${b[i]}`);max=Math.max(max,x);}return max;}
const sdk=new NativeFidelityCPU(await loadVapor(await readFile(wasm))),rows=[];
for(const c of manifest.cases){const id=c.id,e=c.extent,terrain=c.terrain?await floats(id+'.terrain.f32'):undefined,settings={seed:c.seed,coverage:c.coverage,humidity:c.humidity,erosion:c.erosion,wind:c.wind};
 const f=sdk.generate(c.key,{cells:c.cells,extent:e,settings,time:c.time,terrain}),d=await floats(id+'.density.f32'),t=await floats(id+'.temperature.f32');
 const de=check(f.fields.density,d,2e-6,2e-6,id+' density');check(f.fields.temperature,t,0,0,id+' temperature');
 const scene=c.terrain?{depth:await floats(id+'.depth.f32'),radiance:await floats(id+'.scene.f32')}:undefined;
 const img=sdk.render({cells:c.cells,extent:e,densityCap:1,fields:{density:d,temperature:t}},{eye:[e[0]*.65,e[1]*.22,-e[2]*1.5],target:e.map(v=>v*.5),width:64,height:40,steps:48,fov:40,exposure:.95,jitter:.5,background:'sky',scene},{shadowSteps:12});
 rows.push({case:id,max_density_abs_error:de,max_alpha_abs_error:check(img.alpha,await floats(id+'.alpha.f32'),2e-5,2e-5,id+' alpha'),max_rgba_abs_error:check(img.rgba,await raw(id+'.rgba'),1,0,id+' RGBA')});
}
console.log(JSON.stringify(rows));
