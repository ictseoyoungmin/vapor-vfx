/** Fixed common CPU contract. Golden fields and frames come from the actual JS reference.
 * --check regenerates and compares bytes without writing files. No Rust execution.
 */
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {generateFidelityVolume,prepareFidelityVolume} from '../bindings/web/fidelity.mjs';
const dir=new URL('../fixtures/fidelity-port/',import.meta.url);const check=process.argv.includes('--check');if(!check)await mkdir(dir,{recursive:true});
const raw=f=>{const b=Buffer.alloc(f.length*4);for(let i=0;i<f.length;i++)b.writeFloatLE(f[i],4*i);return b;};
const cases=[['cloud','cumulus_cloud',[24,12,16],[144,72,96],43,.53,.76,.23,[.6,0,.22],0,false],['cloud-wind','cumulus_cloud',[24,12,16],[144,72,96],4294967295,.61,.69,.31,[-.8,.12,.42],18.25,false],['fog-terrain','ground_fog',[20,12,18],[60,15,54],18,.72,.88,.13,[.25,0,.10],7,true],['dust','dust',[20,12,16],[20,8,16],65,.57,.75,.22,[.25,0,.15],4,false]];
const manifest=[];
async function emit(name,buffer){const file=new URL(name,dir);if(check){if(!buffer.equals(await readFile(file)))throw Error('fixture drift '+name);}else await writeFile(file,buffer);manifest.push({file:name,sha256:createHash('sha256').update(buffer).digest('hex'),bytes:buffer.length});}
for(const [id,key,cells,extent,seed,coverage,humidity,erosion,wind,time,withTerrain] of cases){
 const [nx,,nz]=cells;const terrain=withTerrain?Float32Array.from({length:nx*nz},(_,i)=>extent[1]*(.10+.16*(i%nx)/(nx-1)+.08*Math.sin(Math.floor(i/nx)*.6))):undefined;
 const volume=generateFidelityVolume(key,{cells,extent,settings:{seed,coverage,humidity,erosion,wind},time,terrain});
 const material={colour:[.91,.96,1],extinction:.32,anisotropy:.55,albedo:.9,emission:0,thermalFade:0,ambient:.10};const lighting={light:{direction:[-.80,.56,.16],radiance:[2.6,2.45,2.2]},sky:[.07,.105,.18],ground:[.035,.04,.05],multiScatter:.29,shadowSteps:12,lightScale:.5};
 const camera={eye:[extent[0]*.65,extent[1]*.22,-extent[2]*1.5],target:extent.map(n=>n*.5),width:64,height:40,steps:48,fov:40,exposure:.95,jitter:.5,background:'sky',skipEmpty:false};
 const scene=withTerrain?{depth:Float32Array.from({length:2560},(_,i)=>i%64<16?extent[2]*.8:0),radiance:Float32Array.from({length:7680},(_,i)=>[.03,.05,.08][i%3])}:undefined;
 const frame=prepareFidelityVolume({...volume,material,...lighting}).render({...camera,scene});
 await emit(id+'.density.f32',raw(volume.fields.density));await emit(id+'.temperature.f32',raw(volume.fields.temperature));await emit(id+'.alpha.f32',raw(frame.alpha));await emit(id+'.linear.f32',raw(frame.linear));await emit(id+'.rgba',Buffer.from(frame.rgba));
 if(terrain)await emit(id+'.terrain.f32',raw(terrain));if(scene){await emit(id+'.depth.f32',raw(scene.depth));await emit(id+'.scene.f32',raw(scene.radiance));}
 console.log(id,volume.fields.density.length,frame.diagnostics.visiblePixels);
}
const json=Buffer.from(JSON.stringify({schema:'vapor.fidelity-port-fixtures/1',evidence:'Actual 0.15 JS Float32 generator and directional optical renderer, NOT Rust execution',cases:cases.map(([id,key,cells,extent,seed,coverage,humidity,erosion,wind,time,terrain])=>({id,key,cells,extent,seed,coverage,humidity,erosion,wind,time,terrain})),files:manifest},null,2)+'\n');
if(check){if(!json.equals(await readFile(new URL('manifest.json',dir))))throw Error('manifest drift');}else await writeFile(new URL('manifest.json',dir),json);
