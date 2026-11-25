/** Actual public JS procedural effects -> CPU raymarch -> temporal history.
 * Reference comparison uses the same field, optics, camera and 192 ray steps.
 * No Rust, GPU, browser or game-engine performance claims. */
import {createEffect} from '../bindings/web/effects.mjs';
import {prepareVolume,ReprojectedPreview} from '../bindings/web/preview.mjs';
import {writeFile,mkdir} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {join} from 'node:path';
const out=process.argv[2];if(!out)throw new Error('Usage: node lab/benchmark_reprojection.mjs output-directory');await mkdir(out,{recursive:true});
const width=240,height=150,steps=12,referenceSteps=192,frameCount=8,rows=[];
const digest=data=>createHash('sha256').update(data).digest('hex');
const median=x=>[...x].sort((a,b)=>a-b)[Math.floor(x.length/2)];
function mse(x,y){let error=0;for(let i=0;i<x.length;i++)if(i%4!==3)error+=(x[i]-y[i])**2;return error/(x.length*.75);}
function camera(extent,key,angle,volumeOrigin=[0,0,0]){const center=extent.map(v=>v/2),span=Math.max(...extent),fog=key==='ground_fog';const dist=span*(fog?1.42:1.52);const eye=[center[0]+Math.sin(angle)*dist,fog?extent[1]+span*.31:center[1]+span*.12,center[2]-Math.cos(angle)*dist];return {eye:eye.map((v,i)=>v+volumeOrigin[i]),target:[center[0],fog?extent[1]*.18:center[1],center[2]].map((v,i)=>v+volumeOrigin[i]),volumeOrigin,background:key==='cumulus_cloud'?'sky':fog?'ground':'dark'};}
function put(sheet,rgba,slot,cols){for(let y=0;y<height;y++)sheet.set(rgba.subarray(y*width*4,(y+1)*width*4),(y*width*cols+slot*width)*4);}
for(const key of ['cumulus_cloud','ground_fog','dust']){
 const effect=await createEffect(key,{quality:'medium'});try{
  effect.play();effect.advance(2);const atlas=await effect.atlasRGBA8();const vol=prepareVolume({atlas,cells:[...effect.renderCells],extent:effect.extent,densityCap:effect.config.densityCap,material:effect.definition.material});
  const history=new ReprojectedPreview(4),frames=[],sheet=new Uint8Array(width*height*4*3);let last;
  for(let i=0;i<frameCount;i++){
   // Camera movement and rigid translation both affect the local viewing ray.
   const base=camera(effect.extent,key,.10+i*.018),origin=[effect.extent[0]*.004*i,0,0],cameraOptions={...base,volumeOrigin:origin};
   const jitter=(.5+i*.61803398875)%1,opts={...cameraOptions,width,height,steps,jitter};
   const t0=performance.now(),frame=vol.renderFrame(opts),raymarchMs=performance.now()-t0;
   const raw=frame.rgba,t1=performance.now(),acc=history.accumulate(key,frame),reprojectionMs=performance.now()-t1;
   const localEye=base.eye.map((v,a)=>v-origin[a]),localTarget=base.target.map((v,a)=>v-origin[a]);
   const t2=performance.now(),reference=vol.render({...base,eye:localEye,target:localTarget,width,height,steps:referenceSteps,jitter:.5}),referenceMs=performance.now()-t2;
   frames.push({frame:i,angle:.10+i*.018,volumeOrigin:origin,jitter,rawMse:mse(raw,reference),temporalMse:mse(acc.rgba,reference),raymarchMs,reprojectionMs,referenceMs,...acc.diagnostics});
   last={raw,temporal:acc.rgba,reference};
  }
  put(sheet,last.raw,0,3);put(sheet,last.temporal,1,3);put(sheet,last.reference,2,3);
  const file=key+'.rgba';await writeFile(join(out,file),sheet);
  const warm=frames.slice(1),avg=f=>warm.reduce((sum,v)=>sum+f(v),0)/warm.length;
  rows.push({key,quality:'medium',cells:[...effect.renderCells],extent:effect.extent,atlasSha256:digest(atlas),file,width:width*3,height,rawImageSha256:digest(sheet),frames,meanRawMse:avg(v=>v.rawMse),meanTemporalMse:avg(v=>v.temporalMse),meanHistoryFraction:avg(v=>v.historyFraction),medianRaymarchMs:median(warm.map(v=>v.raymarchMs)),medianReprojectionMs:median(warm.map(v=>v.reprojectionMs)),medianReferenceMs:median(warm.map(v=>v.referenceMs))});
 }finally{effect.dispose();}
}
await writeFile(join(out,'reprojection.json'),JSON.stringify({schema:'vapor.cpu-preview-reprojection/1',evidence:'actual JS procedural CPU Effect API + software raymarch and reprojection, not native fluid or game renderer',node:process.version,width,height,steps,referenceSteps,frameCount,comparison:'sRGB channel mean squared error against same-camera higher-step reference; not ground truth or perceptual score',rows},null,2)+'\n');
