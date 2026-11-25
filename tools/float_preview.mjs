/** Compare raw Float32 coarse fields against the same fields encoded as RGBA8.
 * No field generator. x-fastest little-endian f32 arrays from a real runtime. */
import {prepareVolume} from '../bindings/web/preview.mjs';
import {createHash} from 'node:crypto';import {readFile,writeFile} from 'node:fs/promises';import {pathToFileURL} from 'node:url';
const hash=b=>createHash('sha256').update(b).digest('hex');
export function compareFields({fields,cells,extent,densityCap,material,width=320,height=200,steps=96}){
 const n=cells.reduce((a,b)=>a*b,1),atlas=new Uint8Array(n*4);let positive=0,lost=0,total=0,lostMass=0,quantizedTotal=0;
 const common={cells,extent,densityCap,material},full=prepareVolume({...common,fields});
 for(let i=0;i<n;i++){const rho=fields.density[i],q=Math.min(255,Math.round(rho/densityCap*255));atlas[i*4]=q;atlas[i*4+1]=Math.min(255,Math.round(fields.temperature[i]/16*255));atlas[i*4+3]=255;total+=rho;quantizedTotal+=q*densityCap/255;if(rho>0){positive++;if(q===0){lost++;lostMass+=rho;}}}
 const old=prepareVolume({...common,atlas}),center=extent.map(x=>x*.5),diag=Math.hypot(...extent),dist=diag/(2*Math.sin(Math.atan(Math.tan(20*Math.PI/180)*Math.min(1,width/height))))*1.08;
 const camera={width,height,steps,eye:[center[0],center[1]+dist*.1,center[2]-dist],target:center,background:'dark'};
 const a=old.render(camera),b=full.render(camera),sheet=new Uint8Array(width*height*8);let changed=0,absolute=0;
 for(let y=0;y<height;y++){sheet.set(a.subarray(y*width*4,(y+1)*width*4),y*width*8);sheet.set(b.subarray(y*width*4,(y+1)*width*4),y*width*8+width*4);}
 for(let i=0;i<a.length;i+=4){const ds=[0,1,2].map(c=>Math.abs(a[i+c]-b[i+c]));changed+=Math.max(...ds)>=2;absolute+=ds[0]+ds[1]+ds[2];}
 return {rgba:sheet,width:width*2,height,camera,positiveVoxels:positive,quantizedToZeroVoxels:lost,positiveDensityFractionLost:total?lostMass/total:0,quantizedDensityRelativeError:total?(quantizedTotal-total)/total:0,changedPixels:changed,meanAbsoluteRGBDifference:absolute/(width*height*3),notice:'Coarse field precision comparison only; temperature is also quantized in the old branch. Not Hybrid fine detail or engine capture.'};
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){const [specFile,densityFile,tempFile,out]=process.argv.slice(2);const spec=JSON.parse(await readFile(specFile,'utf8')),d=await readFile(densityFile),t=await readFile(tempFile);const decode=b=>{if(b.length%4)throw Error('invalid f32 bytes');const a=new Float32Array(b.length/4);for(let i=0;i<a.length;i++)a[i]=b.readFloatLE(i*4);return a;};const {rgba,...report}=compareFields({...spec,fields:{density:decode(d),temperature:decode(t)}});await writeFile(out,rgba);console.log(JSON.stringify({...report,densitySha256:hash(d),temperatureSha256:hash(t)}));}
