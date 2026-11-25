/** Render packet plume with unchanged material plus fixed authoring calibration.
 * Target opacities are design choices, NOT measured tobacco or aerosol optical properties. */
import {readFile,writeFile,mkdir} from 'node:fs/promises';import {join} from 'node:path';import {spawnSync} from 'node:child_process';import {createHash} from 'node:crypto';
import {prepareFidelityVolume,getFidelityPreset} from '../bindings/web/fidelity.mjs';import {fitOpacityFromProbe} from './optical_calibration.mjs';
const [input,out]=process.argv.slice(2);if(!input||!out)throw Error('input/output required');await mkdir(out,{recursive:true});const report=JSON.parse(await readFile(join(input,'experiment.json'),'utf8'));if(report.status!=='PASS_EXECUTION_ONLY')throw Error('experiment incomplete');
const decode=b=>{const a=new Float32Array(b.length/4);for(let i=0;i<a.length;i++)a[i]=b.readFloatLE(i*4);return a;};
async function get(stem){const spec=JSON.parse(await readFile(join(input,stem+'.json'),'utf8'));return {...spec,fields:{density:decode(await readFile(join(input,stem+'.density.f32'))),temperature:decode(await readFile(join(input,stem+'.temperature.f32')))}};}
function save(img,camera,file){const r=spawnSync(process.env.PYTHON??'python',['-c','from PIL import Image;import sys;Image.frombytes("RGBA",(int(sys.argv[1]),int(sys.argv[2])),sys.stdin.buffer.read()).save(sys.argv[3])',String(camera.width),String(camera.height),join(out,file)],{input:img.rgba});if(r.status!==0)throw Error(String(r.stderr));}
const rows=[];
for(const row of report.rows.filter(x=>x.model==='packets')){
 const smoke=row.key==='cigarette_smoke',camera=smoke?{width:360,height:580,eye:[.20,.47,-1.23],target:[.20,.47,.20],fov:38,steps:224,exposure:1,background:'dark'}:{width:640,height:360,eye:[1.10,.60,-2.45],target:[1.10,.60,.60],fov:34,steps:224,exposure:1,background:'dark'};
 const lighting={...getFidelityPreset(row.key).lighting,lightScale:.5,shadowSteps:24},anchor=row.snapshots.reduce((a,b)=>Math.abs(a.time-2)<Math.abs(b.time-2)?a:b),v=await get(anchor.stem);
 const probe=prepareFidelityVolume({...v,material:{...v.material,extinction:1},...lighting}).render(camera);let fit;
 try{fit=fitOpacityFromProbe(probe.alpha,{targetOpacity:smoke?.55:.72,minAlpha:1e-5});}catch(e){rows.push({effect:row.key,status:'NOT_FIT',reason:String(e)});continue;}
 const result={effect:row.key,status:'PASS_AUTHORING_ONLY',anchorTime:anchor.time,anchor:anchor.stem,originalExtinction:v.material.extinction,fit,rows:[]};
 for(const snap of row.snapshots){const f=await get(snap.stem),frame=prepareFidelityVolume({...f,material:{...f.material,extinction:fit.extinction},...lighting}).render(camera),file=snap.stem+'-calibrated.png';save(frame,camera,file);result.rows.push({time:snap.time,file,extinction:fit.extinction,visiblePixels:frame.diagnostics.visiblePixels,rgbaSha256:createHash('sha256').update(frame.rgba).digest('hex')});console.log(file,fit.extinction,frame.diagnostics.visiblePixels);}
 rows.push(result);
}
await writeFile(join(out,'calibration.json'),JSON.stringify({scope:'Lab-only one-time Beer-Lambert calibration from a fixed anchor; not measured physical opacity or production preset change',rows},null,2)+'\n');
