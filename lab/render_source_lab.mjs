/** Actual independent CPU field renders with original preset material (no extinction boost). */
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {join} from 'node:path';
import {prepareFidelityVolume,getFidelityPreset} from '../bindings/web/fidelity.mjs';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
const [input,out]=process.argv.slice(2);await mkdir(out,{recursive:true});
const report=JSON.parse(await readFile(join(input,'experiment.json'),'utf8'));if(report.status!=='PASS')throw Error('experiment did not complete');
const decode=b=>{const a=new Float32Array(b.length/4);for(let i=0;i<a.length;i++)a[i]=b.readFloatLE(i*4);return a;};
const rows=[];
for(const row of report.rows){
 const stem=row.snapshots.at(-1).stem,spec=JSON.parse(await readFile(join(input,stem+'.json'),'utf8')),raw=await readFile(join(input,stem+'.density.f32')),temp=await readFile(join(input,stem+'.temperature.f32'));const fields={density:decode(raw),temperature:decode(temp)};
 const {lighting}=getFidelityPreset(spec.effect);const smoke=spec.effect==='cigarette_smoke';
 const camera=smoke?{width:320,height:360,eye:[.12,.075,-.115],target:[.12,.075,.12],fov:30,steps:160,exposure:1,background:'dark'}:{width:400,height:300,eye:[.19,.37,-.12],target:[.19,.37,.4],fov:35,steps:144,exposure:1,background:'dark'};
 const img=prepareFidelityVolume({...spec,fields,...lighting,material:spec.material,lightScale:.5,shadowSteps:20}).render(camera);
 const file=`${row.key}-${row.scale}x-${row.mode}.png`,res=spawnSync(process.env.PYTHON??'python',['-c','from PIL import Image; import sys; Image.frombytes("RGBA",(int(sys.argv[1]),int(sys.argv[2])),sys.stdin.buffer.read()).save(sys.argv[3])',String(camera.width),String(camera.height),join(out,file)],{input:img.rgba});if(res.status!==0)throw Error(String(res.stderr));
 rows.push({file,stem,camera,material:spec.material,lighting,visiblePixels:img.diagnostics.visiblePixels,densitySha256:createHash('sha256').update(raw).digest('hex'),temperatureSha256:createHash('sha256').update(temp).digest('hex')});console.log(file,img.diagnostics.visiblePixels);
}
await writeFile(join(out,'render.json'),JSON.stringify({evidence:'Actual independent SciPy MAC fields rendered by JS CPU optics; original material, early plume; not Rust/GPU',rows},null,2));
