/** Render an existing, actual RGBA8 density/temperature atlas. Never creates a fluid field.
 * Two panels: fixed-domain view for cross-backend comparison, density-framed detail.
 * Both use the same cached volumetric lighting and optical preset.
 */
import {prepareVolume} from '../bindings/web/preview.mjs';
import {readFile,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
const norm=v=>Math.hypot(...v);
export function summarizeAtlas(atlas,cells,extent,densityCap){
 const [nx,ny,nz]=cells;
 if(!(atlas instanceof Uint8Array)||cells.length!==3||cells.some(v=>!Number.isInteger(v)||v<4||v>768)||nx*ny*nz>2097152||atlas.length!==nx*ny*nz*4||extent.length!==3||extent.some(v=>!Number.isFinite(v)||v<=0)||!Number.isFinite(densityCap)||densityCap<=0)throw new RangeError('invalid atlas metadata');
 let total=0,occupied=0,max=0;const centroid=[0,0,0],lo=[nx,ny,nz],hi=[-1,-1,-1];let index=0;
 for(let z=0;z<nz;z++)for(let y=0;y<ny;y++)for(let x=0;x<nx;x++,index+=4){
   if(atlas[index+3]!==255)throw new Error('atlas alpha channel is not 255');
   const d=atlas[index];if(!d)continue;total+=d;occupied++;max=Math.max(max,d);
   const p=[x,y,z];for(let i=0;i<3;i++){lo[i]=Math.min(lo[i],p[i]);hi[i]=Math.max(hi[i],p[i]);centroid[i]+=d*(p[i]+.5);}
 }
 if(!occupied)throw new Error('empty quantized density atlas');
 const dx=extent.map((v,i)=>v/cells[i]);
 return {occupiedVoxels:occupied,occupiedFraction:occupied/(nx*ny*nz),maxDensityByte:max,
  quantizedDensityIntegral:total*densityCap/255*dx.reduce((a,b)=>a*b,1),
  centroid:centroid.map((v,i)=>v/total*dx[i]),boundsMin:lo.map((v,i)=>v*dx[i]),boundsMax:hi.map((v,i)=>(v+1)*dx[i])};
}
function countVisible(a,b){let count=0,max=0;for(let i=0;i<a.length;i+=4){const d=Math.max(Math.abs(a[i]-b[i]),Math.abs(a[i+1]-b[i+1]),Math.abs(a[i+2]-b[i+2]));if(d>=2)count++;max=Math.max(max,d);}return {visiblePixels:count,maxChannelDifference:max};}
export function renderAtlasViews({atlas,cells,extent,densityCap,material,background='dark',width=384,height=256,steps=96}){
 const stats=summarizeAtlas(atlas,cells,extent,densityCap),center=extent.map(v=>v/2),span=Math.max(...extent);
 const dir=[.26,.10,-1],u=dir.map(v=>v/norm(dir));
 const eyeAt=(target,distance)=>target.map((v,i)=>v+u[i]*distance);
 const target=stats.boundsMin.map((v,i)=>(v+stats.boundsMax[i])/2);
 const detailSpan=Math.max(...stats.boundsMax.map((v,i)=>v-stats.boundsMin[i]));
 // Fit a bounding sphere against the smaller camera FOV. Fixed view always retains
 // identical camera coordinates across modes; detail framing is explicitly data-dependent.
 const half=Math.atan(Math.tan(20*Math.PI/180)*Math.min(1,width/height));
 const fit=ext=>norm(ext)*.5/Math.sin(half)*1.08;
 const fixedDist=fit(extent),detailDist=Math.max(fit(stats.boundsMax.map((v,i)=>v-stats.boundsMin[i])),span*.18);
 const views=[{name:'domain',target:center,eye:eyeAt(center,fixedDist)},{name:'density-detail',target,eye:eyeAt(target,detailDist)}];
 const prepared=prepareVolume({atlas,cells,extent,densityCap,material});
 // Identical empty scene (no field substitution for the actual image): verifies the
 // rendered effect contributes visible pixels, even on an opaque background.
 const empty=new Uint8Array(4*4*4*4);for(let i=3;i<empty.length;i+=4)empty[i]=255;
 const bg=prepareVolume({atlas:empty,cells:[4,4,4],extent,densityCap,material});
 const sheet=new Uint8Array(width*2*height*4),reports=[];
 for(let panel=0;panel<views.length;panel++){
  const view=views[panel],options={width,height,steps,background,eye:view.eye,target:view.target};
  const frame=prepared.render(options),blank=bg.render(options),visible=countVisible(frame,blank);
  if(!visible.visiblePixels)throw new Error(`atlas produced no visible pixels (${view.name})`);
  for(let y=0;y<height;y++)sheet.set(frame.subarray(y*width*4,(y+1)*width*4),(y*width*2+panel*width)*4);
  reports.push({...view,...visible});
 }
 return {rgba:sheet,width:width*2,height,stats,views:reports,detailSpan,atlasSha256:createHash('sha256').update(atlas).digest('hex')};
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
 const [metadata,input,output]=process.argv.slice(2);if(!metadata||!input||!output)throw new Error('Usage: node tools/atlas_preview.mjs metadata.json atlas.rgba output.rgba');
 const spec=JSON.parse(await readFile(metadata,'utf8')),atlas=new Uint8Array(await readFile(input));
 const start=performance.now(),result=renderAtlasViews({...spec,atlas});const {rgba,...report}=result;
 await writeFile(output,rgba);console.log(JSON.stringify({...report,previewMs:performance.now()-start,evidence:'CPU software ray march of supplied atlas; not an engine screenshot or solver execution'}));
}
