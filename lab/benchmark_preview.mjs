/** Same-process CPU preview comparison, optional older checkout. No GPU or game FPS claim. */
import {performance} from 'node:perf_hooks';
import {pathToFileURL} from 'node:url';
import {resolve} from 'node:path';
import {writeFile,mkdir} from 'node:fs/promises';
await mkdir(new URL('../reports/local/lab/',import.meta.url),{recursive:true});
import {createEffect} from '../bindings/web/effects.mjs';
import {prepareVolume,renderVolume} from '../bindings/web/preview.mjs';
const baseline=process.argv[2]?await import(pathToFileURL(resolve(process.argv[2],'bindings/web/preview.mjs'))):null;
const reports=[];
for(const key of ['cumulus_cloud','ground_fog','dust']){
 const e=await createEffect(key,{quality:'high'}),atlas=await e.atlasRGBA8(),extent=e.extent,center=extent.map(x=>x/2),span=Math.max(...extent),fog=e.definition.kind==='fog';
 const volume={atlas,cells:[...e.renderCells],extent,densityCap:e.config.densityCap,material:e.definition.material};
 const cameras=[.3,.55,.8].map(angle=>({width:320,height:200,steps:64,eye:[center[0]+Math.sin(angle)*span*1.42,fog?extent[1]+span*.22:center[1]+span*.12,center[2]-Math.cos(angle)*span*1.42],target:[center[0],fog?extent[1]*.18:center[1],center[2]],background:fog?'ground':'sky'}));
 renderVolume({...volume,...cameras[0],width:80,height:50,steps:24});if(baseline)baseline.renderVolume({...volume,...cameras[0],width:80,height:50,steps:24});
 const elapsed=fn=>{const t=performance.now();const out=fn();if(!(out instanceof Uint8Array))throw Error('expected actual pixels');return +(performance.now()-t).toFixed(1);};
 const before=baseline?cameras.map(c=>elapsed(()=>baseline.renderVolume({...volume,...c}))):null;
 const t=performance.now(),p=prepareVolume(volume),prepareMs=+(performance.now()-t).toFixed(1),views=cameras.map(c=>elapsed(()=>p.render(c))),sum=xs=>xs.reduce((a,b)=>a+b,0);
 reports.push({key,cells:e.renderCells,width:320,height:200,steps:64,oldPerViewMs:before,prepareMs,newPerViewMs:views,oldTotalMs:before?+sum(before).toFixed(1):null,newTotalMs:+(prepareMs+sum(views)).toFixed(1)});e.dispose();console.log(reports.at(-1));
}
await writeFile(new URL('../reports/local/lab/preview-benchmark.json',import.meta.url),JSON.stringify({evidence:'Actual Node CPU preview with identical atlas, camera and image sizes; updated shadow integration changes pixels. Single run, not controlled FPS benchmark.',node:process.version,baseline:baseline?'0.6 checkout supplied by caller':null,reports},null,2)+'\n');
