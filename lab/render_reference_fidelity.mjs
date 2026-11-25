/** Actual independent reference snapshots, same camera/material per effect. */
import {readFile,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {prepareFidelityVolume} from '../bindings/web/fidelity.mjs';
const dir=new URL('../reports/local/lab/fidelity/',import.meta.url),detailOnly=process.argv.includes('--detail-only'),rows=detailOnly?JSON.parse(await readFile(new URL('plume-comparison.json',dir),'utf8')).rows.filter(r=>!r.name.endsWith('-detail')):[];
const decode=b=>{const a=new Float32Array(b.length/4);for(let i=0;i<a.length;i++)a[i]=b.readFloatLE(i*4);return a;};
const hash=b=>createHash('sha256').update(b).digest('hex');
const cases=detailOnly?[['reference-detail','detail','detail']]:[['reference-medium','medium','baseline'],['reference-turbulent','medium','forced'],['reference-high','high','high'],['reference-detail','detail','detail']];
for(const key of ['cigarette_smoke','exhaled_aerosol'])for(const [folder,quality,label] of cases){
 const stem=`${folder}/${key}-${quality}-0120`,spec=JSON.parse(await readFile(new URL(stem+'.json',dir),'utf8')),d=await readFile(new URL(stem+'.density.f32',dir)),t=await readFile(new URL(stem+'.temperature.f32',dir));
 const smoke=key==='cigarette_smoke',material={...spec.material,extinction:smoke?135:14,ambient:.03,colour:smoke?[.72,.81,.96]:[.94,.96,1]},lighting={light:{direction:[-.82,.49,.19],radiance:smoke?[2.2,2.4,2.8]:[1.8,1.9,2.1]},sky:[.016,.024,.037],ground:[.008,.012,.018],multiScatter:.14};
 const camera=smoke?{width:420,height:560,eye:[.14,.20,-.48],target:[.12,.20,.12],fov:39,steps:256,exposure:1.15,background:'dark'}:{width:700,height:420,eye:[.48,.44,-.84],target:[.47,.40,.4],fov:40,steps:224,exposure:1.05,background:'dark'};
 const start=performance.now(),p=prepareFidelityVolume({...spec,fields:{density:decode(d),temperature:decode(t)},material,...lighting,lightScale:quality==='detail'?.5:1,shadowSteps:32}),prep=performance.now()-start,now=performance.now(),img=p.render(camera),ms=performance.now()-now,name=`${key}-compare-${label}`;
 await writeFile(new URL(name+'.rgba',dir),img.rgba);rows.push({name,width:camera.width,height:camera.height,camera,material,lighting,time:spec.time,source:spec.evidence,fieldSource:stem,cells:spec.cells,densitySha256:hash(d),temperatureSha256:hash(t),rgbaSha256:hash(img.rgba),prepareMs:prep,renderMs:ms,diagnostics:img.diagnostics});console.log(name,ms.toFixed(1));
}
await writeFile(new URL('plume-comparison.json',dir),JSON.stringify({status:'PASS',evidence:'Independent actual SciPy MAC fields; same new reference renderer, not Rust or measured real smoke',rows},null,2)+'\n');
