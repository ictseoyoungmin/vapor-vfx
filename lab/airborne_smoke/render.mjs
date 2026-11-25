import {readFile,writeFile} from 'node:fs/promises';
import {prepareFidelityVolume} from '../../bindings/web/fidelity.mjs';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {resolve} from 'node:path';
import {mkdir} from 'node:fs/promises';
const root=pathToFileURL(resolve(process.env.VAPOR_AIRBORNE_OUTPUT??fileURLToPath(new URL('../../reports/local/lab/airborne-smoke',import.meta.url)))+'/');
await mkdir(new URL('renders/',root),{recursive:true});
const cfg=JSON.parse(await readFile(new URL('config.json',root),'utf8'));
const {cells,extent,width,height}=cfg;
const camera={width,height,eye:[7.0,5.55,-13.0],target:[7.0,5.55,4.7],fov:34,steps:144,exposure:1.05,background:'sky'};
const material={colour:[.072,.067,.064],extinction:5.8,anisotropy:.19,albedo:.78,emission:7.6,thermalFade:0,ambient:.035};
const lighting={light:{direction:[.76,.64,-.18],radiance:[5.4,5.0,4.5]},sky:[.16,.22,.31],ground:[.042,.045,.052],multiScatter:.19,shadowSteps:28,lightScale:.625};
const f32=b=>new Float32Array(b.buffer,b.byteOffset,b.byteLength/4).slice();
const background=f32(await readFile(new URL('background.f32',root))),depth=new Float32Array(width*height),zero=new Float32Array(cells.reduce((a,b)=>a*b));
for(const i of process.argv.slice(2).map(Number)){
 const s=String(i).padStart(4,'0'),start=performance.now();let fields={density:zero,temperature:zero};
 if(i>0)fields={density:f32(await readFile(new URL('fields/'+s+'.rho',root))),temperature:f32(await readFile(new URL('fields/'+s+'.heat',root)))};
 const t=Math.max(0,Math.min(1,(i/cfg.fps-5.3)/1.35));const lift=.78*t*t*(3-2*t);const shot={...camera,eye:[camera.eye[0],camera.eye[1]+lift,camera.eye[2]],target:[camera.target[0],camera.target[1]+lift,camera.target[2]]};
 const result=prepareFidelityVolume({fields,cells,extent,densityCap:1,material,...lighting}).render({...shot,scene:{depth,radiance:background}});
 await writeFile(new URL('renders/'+s+'.rgba',root),result.rgba);
 if(i<=31)await writeFile(new URL('renders/'+s+'.alpha',root),new Uint8Array(result.alpha.buffer));
 await writeFile(new URL('renders/'+s+'.json',root),JSON.stringify({frame:i,ms:performance.now()-start,...result.diagnostics}));console.log(s,Math.round(performance.now()-start),result.diagnostics.visiblePixels);
}
