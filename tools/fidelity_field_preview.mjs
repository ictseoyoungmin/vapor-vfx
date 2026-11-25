/** Render arbitrary actual native or external Float32 fields. No density generation. */
import {readFile,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {getFidelityPreset,prepareFidelityVolume} from '../bindings/web/fidelity.mjs';
const [specFile,densityFile,tempFile,out]=process.argv.slice(2),spec=JSON.parse(await readFile(specFile,'utf8')),d=await readFile(densityFile),t=await readFile(tempFile);
const decode=b=>{if(b.length%4)throw Error('invalid float bytes');const a=new Float32Array(b.length/4);for(let i=0;i<a.length;i++)a[i]=b.readFloatLE(i*4);return a;},hash=b=>createHash('sha256').update(b).digest('hex');
const style=getFidelityPreset(spec.effect??'smoke'),m={...style.material,...spec.material},center=spec.extent.map(x=>x*.5),dist=Math.hypot(...spec.extent)*1.8;
const camera={width:480,height:360,steps:144,eye:[center[0],center[1]+dist*.1,center[2]-dist],target:center,background:'dark',...spec.camera};
const start=performance.now(),p=prepareFidelityVolume({...spec,fields:{density:decode(d),temperature:decode(t)},material:m,...style.lighting,lightScale:.75,shadowSteps:32}),prep=performance.now()-start,now=performance.now(),f=p.render(camera);
await writeFile(out,f.rgba);console.log(JSON.stringify({width:camera.width,height:camera.height,camera,material:m,lighting:style.lighting,densitySha256:hash(d),temperatureSha256:hash(t),rgbaSha256:hash(f.rgba),diagnostics:f.diagnostics,prepareMs:prep,renderMs:performance.now()-now,notice:'High-fidelity CPU reference rendering of supplied field; caller must establish actual field provenance. Not GPU rendering.'}));
