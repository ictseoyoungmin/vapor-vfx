/** Real CPU render of identical Float32 fields with several optical-cache sizes.
 * Not a GPU benchmark. Inputs are the saved independent 0.13 simulation fields. */
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {prepareFidelityVolume,generateFidelityVolume,getFidelityPreset} from '../bindings/web/fidelity.mjs';
import {packFidelityLighting} from '../bindings/web/gpu-fidelity.mjs';
const out=new URL('../reports/local/lab/fidelity-cache/',import.meta.url);await mkdir(out,{recursive:true});
const dir=new URL('../reports/local/lab/fidelity/',import.meta.url),meta=JSON.parse(await readFile(new URL('plume-comparison.json',dir),'utf8'));
const decode=b=>{const a=new Float32Array(b.length/4);for(let i=0;i<a.length;i++)a[i]=b.readFloatLE(i*4);return a;};
const hash=b=>createHash('sha256').update(Buffer.isBuffer(b)?b:Buffer.from(b.buffer,b.byteOffset,b.byteLength)).digest('hex');
const cases=[];
for(const key of ['cigarette_smoke','exhaled_aerosol']){
 const m=meta.rows.find(r=>r.name===`${key}-compare-detail`);const stem=m.fieldSource,s=JSON.parse(await readFile(new URL(stem+'.json',dir),'utf8')),d=await readFile(new URL(stem+'.density.f32',dir)),t=await readFile(new URL(stem+'.temperature.f32',dir));
 cases.push({key,source:s.evidence,volume:{...s,fields:{density:decode(d),temperature:decode(t)}},material:m.material,lighting:m.lighting,camera:{...m.camera,width:key==='cigarette_smoke'?225:360,height:key==='cigarette_smoke'?300:216,steps:112}});
}
const cloud=generateFidelityVolume('cumulus_cloud',{cells:[96,48,64],extent:[144,72,96]}),style=getFidelityPreset('cumulus_cloud');cases.push({key:'cumulus_cloud',source:'Actual JS generated procedural field',volume:cloud,material:style.material,lighting:style.lighting,camera:{width:360,height:225,eye:[110,15,-150],target:[72,32,48],fov:40,steps:112,exposure:.95}});
const rows=[];
for(const {key,source,volume,material,lighting,camera} of cases){
 const frames=[];for(const scale of [1,.5,.25]){
   const start=performance.now(),p=prepareFidelityVolume({...volume,material,...lighting,lightScale:scale,shadowSteps:24}),prepMs=performance.now()-start,now=performance.now(),frame=p.render(camera),renderMs=performance.now()-now;
   let rmse=0,foregroundRmse=0,max=0,alphaDelta=0,foreground=frame.alpha.reduce((n,a)=>n+Number(a>.01),0);if(frames.length){const ref=frames[0].frame;let sum=0,fgSum=0;for(let i=0;i<frame.rgba.length;i++){if(i%4===3)continue;const d=frame.rgba[i]-ref.rgba[i];sum+=d*d;if(ref.alpha[i>>2]>.01)fgSum+=d*d;max=Math.max(max,Math.abs(d));}rmse=Math.sqrt(sum/(frame.alpha.length*3));foregroundRmse=Math.sqrt(fgSum/Math.max(foreground*3,1));for(let i=0;i<frame.alpha.length;i++)alphaDelta=Math.max(alphaDelta,Math.abs(frame.alpha[i]-ref.alpha[i]));if(alphaDelta!==0)throw Error('lighting cache changed alpha');}
   const file=`${key}-${scale}.rgba`;await writeFile(new URL(file,out),frame.rgba);
   let gpuPlan;try{const b=packFidelityLighting(volume,{lightScale:scale,lightSteps:24});gpuPlan={cells:b.cells,bytes:b.cacheBytes,raySamples:b.count*24};}catch(e){gpuPlan={rejected:String(e.message)};}
   frames.push({frame,row:{scale,file,width:camera.width,height:camera.height,rgbaSha256:hash(frame.rgba),prepMs,renderMs,rgbRmse255:rmse,foregroundRgbRmse255:foregroundRmse,foregroundPixels:foreground,maxRgbDelta255:max,alphaDelta,lightCells:frame.diagnostics.lightCells,gpuPlan}});console.log(key,scale,rmse.toFixed(4),prepMs.toFixed(1),renderMs.toFixed(1));
 }
 rows.push({key,source,cells:volume.cells,densitySha256:hash(volume.fields.density),temperatureSha256:hash(volume.fields.temperature),camera,material,lighting,frames:frames.map(x=>x.row)});
}
await writeFile(new URL('cache-audit.json',out),JSON.stringify({status:'PASS',evidence:'Actual JS CPU renders of fixed Float32 fields; CPU cache resolution comparison, NOT GPU timings or GPU shader execution',reference:'100% cache, 24 midpoint sunlight samples',rows},null,2)+'\n');
