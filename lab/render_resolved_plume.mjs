/** Actual local uniform MAC/DST research fields, original material, fixed camera. */
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {join} from 'node:path';
import {prepareFidelityVolume,getFidelityPreset} from '../bindings/web/fidelity.mjs';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
const [input,out]=process.argv.slice(2);if(!input||!out)throw Error('input/output required');await mkdir(out,{recursive:true});
const report=JSON.parse(await readFile(join(input,'experiment.json'),'utf8'));if(report.status!=='PASS_EXECUTION_ONLY')throw Error('experiment incomplete');
const decode=b=>{const a=new Float32Array(b.length/4);for(let i=0;i<a.length;i++)a[i]=b.readFloatLE(i*4);return a;};
const rows=[];
for(const row of report.rows)for(const snapshot of row.snapshots){
 const stem=snapshot.stem,spec=JSON.parse(await readFile(join(input,stem+'.json'),'utf8')),raw=await readFile(join(input,stem+'.density.f32')),temp=await readFile(join(input,stem+'.temperature.f32'));
 const {lighting}=getFidelityPreset(spec.effect),smoke=spec.effect==='cigarette_smoke';
 const camera=smoke?{width:260,height:340,eye:[.054,.108,-.34],target:[.054,.108,.054],fov:34,steps:160,exposure:1,background:'dark'}:{width:340,height:250,eye:[.32,.16,-.80],target:[.32,.16,.16],fov:34,steps:160,exposure:1,background:'dark'};
 const img=prepareFidelityVolume({...spec,fields:{density:decode(raw),temperature:decode(temp)},...lighting,material:spec.material,lightScale:.5,shadowSteps:20}).render(camera);
 const file=stem+'.png',res=spawnSync(process.env.PYTHON??'python',['-c','from PIL import Image;import sys;Image.frombytes("RGBA",(int(sys.argv[1]),int(sys.argv[2])),sys.stdin.buffer.read()).save(sys.argv[3])',String(camera.width),String(camera.height),join(out,file)],{input:img.rgba});if(res.status!==0)throw Error(String(res.stderr));
 rows.push({file,stem,effect:row.key,model:row.model,time:snapshot.time,camera,material:spec.material,lighting,visiblePixels:img.diagnostics.visiblePixels,densitySha256:createHash('sha256').update(raw).digest('hex'),temperatureSha256:createHash('sha256').update(temp).digest('hex')});console.log(file,img.diagnostics.visiblePixels);
}
await writeFile(join(out,'render.json'),JSON.stringify({evidence:'Actual independent SciPy/Numba MAC/DST fields rendered by JS CPU optics; original material, not Rust/GPU',rows},null,2));
