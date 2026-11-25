/** Bake canonical cloud and terrain-fog fields, with lossless readback and rendered proof. */
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {generateFidelityVolume,prepareFidelityVolume,getFidelityPreset} from '../bindings/web/fidelity.mjs';
import {encodeFieldAsset,decodeFieldAsset} from '../bindings/web/field-asset.mjs';
import {valleyTerrain,createValleyScene} from '../examples/high-fidelity/valley.mjs';
const [out,profile='hero']=process.argv.slice(2);if(!out)throw Error('usage: node tools/bake_field_assets.mjs OUTPUT [hero|preview]');
await mkdir(out,{recursive:true});const s=JSON.parse(await readFile(new URL('../contracts/cloud-hero.json',import.meta.url),'utf8')),p=s.profiles[profile];if(!p)throw Error('unknown profile');
const hash=b=>createHash('sha256').update(b).digest('hex');
function png(frame,w,h,file){const result=spawnSync(process.env.PYTHON??'python',['-c','from PIL import Image;import sys;Image.frombytes("RGBA",(int(sys.argv[1]),int(sys.argv[2])),sys.stdin.buffer.read()).save(sys.argv[3])',String(w),String(h),file],{input:frame.rgba});if(result.status!==0)throw Error(String(result.stderr));}
const rows=[];
async function bake(name,volume,material,lighting,camera,sceneOptions={}){
 const bytes=encodeFieldAsset(volume,0),decoded=decodeFieldAsset(bytes),file=name+'.vpf';
 const before=prepareFidelityVolume({...volume,material,...lighting,...sceneOptions}).render(camera);
 const after=prepareFidelityVolume({...decoded,material,...lighting,...sceneOptions}).render(camera);
 if(!Buffer.from(before.rgba).equals(Buffer.from(after.rgba))||!Buffer.from(before.alpha.buffer).equals(Buffer.from(after.alpha.buffer)))throw Error('lossless field render mismatch');
 if(!Buffer.from(bytes).equals(Buffer.from(encodeFieldAsset(decoded,decoded.time))))throw Error('byte roundtrip mismatch');
 await writeFile(join(out,file),bytes);png(after,camera.width,camera.height,join(out,name+'.png'));
 const metadata={schema:'vapor.baked-field/1',source:'actual JS Fidelity reference, not Rust',preset:name==='cloud'?'cumulus_cloud':'ground_fog',file,sha256:hash(bytes),cells:decoded.cells,extent:decoded.extent,densityCap:decoded.densityCap,time:decoded.time,material,lighting,camera:Object.fromEntries(Object.entries(camera).filter(([k])=>k!=='scene')),scene:name==='fog'?'analytic valley depth and sun visibility supplied by demo':'sky',rgbaSha256:hash(after.rgba),visiblePixels:after.diagnostics.visiblePixels,losslessRoundtrip:true,bytes:bytes.length};
 await writeFile(join(out,name+'.json'),JSON.stringify(metadata,null,2)+'\n');rows.push(metadata);console.log('baked',name,bytes.length,'visible',metadata.visiblePixels);
}
await bake('cloud',generateFidelityVolume(s.preset,{quality:s.quality,cells:p.cells,extent:s.extent,settings:s.settings,time:s.time}),s.material,s.lighting,{...s.camera,width:p.width,height:p.height,steps:p.steps});
const cells=[96,24,96],extent=[60,15,60],terrain=valleyTerrain(cells,extent),camera={width:800,height:500,eye:[29.8,6.5,-6],target:[30,3.9,34],fov:47,steps:160,exposure:1.0},light={direction:[.60,.34,.72],radiance:[.95,.80,.62]},valley=createValleyScene(camera,light.direction);
await bake('fog',generateFidelityVolume('ground_fog',{cells,extent,terrain,settings:{coverage:.42,humidity:.64}}),{...getFidelityPreset('ground_fog').material,extinction:.10,anisotropy:.25,ambient:.08,colour:[.89,.91,.96]},{light,sky:[.07,.105,.16],ground:[.015,.020,.018],multiScatter:.13,shadowSteps:32,lightScale:.5},{...camera,scene:valley.scene},{sunVisibility:valley.sunVisibility});
await writeFile(join(out,'validation.json'),JSON.stringify({status:'PASS',scope:'actual JS Float32 field and render roundtrip, not native runtime',rows},null,2)+'\n');
