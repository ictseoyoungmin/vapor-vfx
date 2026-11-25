/** CPU preview ray marcher for actual atlas data. Perspective, Beer-Lambert absorption,
 * bounded single-scattering light cache + HG phase, thermal-opacity and emission proxies.
 * No game renderer or fluid solver is substituted. Output: opaque sRGB RGBA8. */
const clamp=(x,a=0,b=1)=>Math.max(a,Math.min(b,x));
const add=(a,b)=>a.map((x,i)=>x+b[i]), sub=(a,b)=>a.map((x,i)=>x-b[i]), mul=(a,s)=>a.map(x=>x*s), dot=(a,b)=>a.reduce((s,x,i)=>s+x*b[i],0), cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
function unit(v){const n=Math.hypot(...v);if(!Number.isFinite(n)||n<1e-8)throw new RangeError('degenerate direction');return mul(v,1/n);}
function validVector(v){return Array.isArray(v)&&v.length===3&&v.every(Number.isFinite);}
const temporalFrames=new WeakMap();
const MAX_TEMPORAL_PIXELS=1_000_000;
const srgb=x=>Math.round(255*clamp(x<=.0031308?12.92*x:1.055*Math.pow(x,1/2.4)-.055));
const linear=x=>{x/=255;return x<=.04045?x/12.92:((x+.055)/1.055)**2.4;};
export function hgPhase(g,cosTheta){return (1-g*g)/Math.pow(Math.max(.001,1+g*g-2*g*clamp(cosTheta,-1,1)),1.5);}
// Tight, allocation-free trilinear sampling in the hot loop.
function sampler(field,nx,ny,nz,stride=1,channel=0){
 const row=nx*stride,plane=ny*row;
 return (x,y,z)=>{if(x<0||x>1||y<0||y>1||z<0||z>1)return 0;
 let a=clamp(x*nx-.5,0,nx-1),b=clamp(y*ny-.5,0,ny-1),c=clamp(z*nz-.5,0,nz-1);const i=Math.floor(a),j=Math.floor(b),k=Math.floor(c);a-=i;b-=j;c-=k;
 const base=i*stride+j*row+k*plane+channel,ix=i<nx-1?stride:0,iy=j<ny-1?row:0,iz=k<nz-1?plane:0;
 const u=field[base]+a*(field[base+ix]-field[base]),v=field[base+iy]+a*(field[base+iy+ix]-field[base+iy]),w=field[base+iz]+a*(field[base+iz+ix]-field[base+iz]),q=field[base+iz+iy]+a*(field[base+iz+iy+ix]-field[base+iz+iy]);
 const t=u+b*(v-u),r=w+b*(q-w);return t+c*(r-t);};
}
/** Prepare one immutable volume snapshot. The light cache is camera-independent.
 * Render different camera views without rebuilding density or light transmittance.
 * Bounded midpoint quadrature covers the full segment to the domain boundary.
 */
export function prepareVolume({atlas,fields,cells,extent,densityCap,material,light=[-.45,.8,.35],shadowSteps=16}){
 if(!Array.isArray(cells)||cells.length!==3||cells.some(n=>!Number.isInteger(n)||n<4||n>768)||cells.reduce((a,n)=>a*n,1)>2097152||!validVector(extent)||extent.some(v=>v<=0||v>1e7)||!Number.isFinite(densityCap)||densityCap<=0||densityCap>100)throw new RangeError('invalid volume');
 const [nx,ny,nz]=cells,n=nx*ny*nz;
 if((atlas===undefined)===(fields===undefined))throw new RangeError('provide exactly one atlas or float fields');
 if(atlas!==undefined&&(!(atlas instanceof Uint8Array)||atlas.length!==n*4))throw new RangeError('atlas length mismatch');
 if(fields!==undefined){
   if(!fields||!(fields.density instanceof Float32Array)||fields.density.length!==n||!(fields.temperature instanceof Float32Array)||fields.temperature.length!==n)throw new RangeError('float field length/type mismatch');
   for(let i=0;i<n;i++)if(!Number.isFinite(fields.density[i])||fields.density[i]<0||fields.density[i]>densityCap*(1+1e-6)||!Number.isFinite(fields.temperature[i])||fields.temperature[i]<0)throw new RangeError('invalid float field value');
 }
 if(!validVector(light)||!material||!validVector(material.colour)||material.colour.some(x=>x<0||x>1))throw new RangeError('invalid light/material');
 for(const [k,a,b] of [['extinction',0,1000],['anisotropy',-.9,.9],['albedo',0,1],['emission',0,10],['thermalFade',0,1],['ambient',0,1]])if(!Number.isFinite(material[k])||material[k]<a||material[k]>b)throw new RangeError('invalid material '+k);
 if(!Number.isInteger(shadowSteps)||shadowSteps<1||shadowSteps>32||n*shadowSteps>48e6)throw new RangeError('shadow work budget exceeded');
 // Copy the input before publishing a reusable snapshot. Callers can mutate their atlas.
 atlas=atlas?.slice();cells=cells.slice();extent=extent.slice();material={...material,colour:material.colour.slice()};
 // The old atlas branch retains its exact arithmetic and output hashes.
 const dir=unit(light),shadowField=new Float32Array(n),cap=densityCap/255;
 const densitySample=fields===undefined?sampler(atlas,nx,ny,nz,4,0):sampler(fields.density.slice(),nx,ny,nz);
 const tempSample=fields===undefined?sampler(atlas,nx,ny,nz,4,1):sampler(fields.temperature.slice(),nx,ny,nz);
 const scale=fields===undefined?cap:1;
 const temperature=fields===undefined?(x,y,z)=>tempSample(x,y,z)*16/255:tempSample;
 const density=material.thermalFade===0?(x,y,z)=>densitySample(x,y,z)*scale:(x,y,z)=>densitySample(x,y,z)*scale*(1-material.thermalFade*(1-Math.exp(-temperature(x,y,z))));
 const sx=dir[0]/extent[0],sy=dir[1]/extent[1],sz=dir[2]/extent[2];let index=0;
 const exit=(p,d)=>d>1e-12?(1-p)/d:d< -1e-12?-p/d:Infinity;
 for(let z=0;z<nz;z++)for(let y=0;y<ny;y++)for(let x=0;x<nx;x++){
   const px=(x+.5)/nx,py=(y+.5)/ny,pz=(z+.5)/nz,step=Math.min(exit(px,sx),exit(py,sy),exit(pz,sz))/shadowSteps;
   let tau=0;for(let j=0;j<shadowSteps;j++){const t=(j+.5)*step;tau+=density(px+sx*t,py+sy*t,pz+sz*t)*step*material.extinction;if(tau>12)break;}shadowField[index++]=Math.exp(-tau);
 }
 const shadow=sampler(shadowField,nx,ny,nz);
 const snapshotIdentity=Object.freeze({});
 function renderInternal({width=400,height=260,steps=64,eye,target,background='sky',jitter=.5,scene}={},capture=false){
 if(![width,height,steps].every(Number.isInteger)||width<1||height<1||width>1600||height>1200||steps<8||steps>256||width*height*steps>48e6||!Number.isFinite(jitter)||jitter<0||jitter>1)throw new RangeError('preview work budget exceeded');
 if(!validVector(eye)||!validVector(target)||!['sky','ground','dark'].includes(background))throw new RangeError('invalid camera/background');
 if(scene!==undefined){
   if(capture)throw new RangeError('scene depth is supported by direct preview only; temporal history requires scene-aware rejection');
   if(!scene||!(scene.depth instanceof Float32Array)||scene.depth.length!==width*height||!(scene.colour instanceof Uint8Array)||scene.colour.length!==width*height*4)throw new RangeError('scene depth/colour size mismatch');
   for(let i=0;i<scene.depth.length;i++)if(!Number.isFinite(scene.depth[i])||scene.depth[i]<0||scene.colour[i*4+3]!==255)throw new RangeError('scene requires finite nonnegative ray distances and opaque sRGB colour');
 }
 if(capture&&width*height>MAX_TEMPORAL_PIXELS)throw new RangeError('temporal preview pixel budget exceeded');
 const f=unit(sub(target,eye)),r=unit(cross(f,[0,1,0])),u=cross(r,f),aspect=width/height,half=Math.tan(40*Math.PI/360),out=new Uint8Array(width*height*4);
 // Separate optical layer from background. Keep one representative local point
 // (opacity-weighted ray distance), not an opaque surface depth.
 const layer=capture?new Float32Array(width*height*4):null,points=capture?new Float32Array(width*height*3):null,bgLinear=capture?new Float32Array(width*height*3):null;
 let pix=0;for(let y=0;y<height;y++)for(let x=0;x<width;x++){
 const d=unit(add(f,add(mul(r,(2*(x+.5)/width-1)*half*aspect),mul(u,(1-2*(y+.5)/height)*half))));
 let near=0,far=Infinity;for(let a=0;a<3;a++){if(Math.abs(d[a])<1e-8){if(eye[a]<0||eye[a]>extent[a]){far=-1;break;}}else{const l=-eye[a]/d[a],h=(extent[a]-eye[a])/d[a];near=Math.max(near,Math.min(l,h));far=Math.min(far,Math.max(l,h));}}
 let bg=background==='dark'?[.012,.02,.035]:[.20+.15*clamp(-d[1]),.39+.15*clamp(-d[1]),.64+.11*clamp(-d[1])];
 if(scene===undefined&&background==='ground'&&d[1]<-1e-6){const ground=-eye[1]/d[1];if(ground>0){far=Math.min(far,ground);const px=eye[0]+d[0]*ground,pz=eye[2]+d[2]*ground;const scale=Math.max(extent[0],extent[2])/12;const grid=(Math.abs(px/scale-Math.round(px/scale))<.018||Math.abs(pz/scale-Math.round(pz/scale))<.018) ? .075*Math.exp(-ground/(Math.max(...extent)*1.1)) : 0;const haze=1-Math.exp(-ground/(Math.max(...extent)*3));bg=[.065+grid+.15*haze,.083+grid+.19*haze,.11+grid+.23*haze];}}
 // Scene colour is the opaque host background, including surfaces beyond the volume.
 if(scene!==undefined){const distance=scene.depth[pix/4];if(distance>0)far=Math.min(far,distance);bg=[linear(scene.colour[pix]),linear(scene.colour[pix+1]),linear(scene.colour[pix+2])];}
 let tr=1,c0=0,c1=0,c2=0,moment=0;const phase=Math.min(4,hgPhase(material.anisotropy,dot(d,dir)));
 if(far>near){const dt=(far-near)/steps;for(let i=0;i<steps&&tr>.003;i++){
 const t=near+(i+jitter)*dt,px=(eye[0]+d[0]*t)/extent[0],py=(eye[1]+d[1]*t)/extent[1],pz=(eye[2]+d[2]*t)/extent[2],den=density(px,py,pz);if(den<.00001)continue;
 const op=1-Math.exp(-den*material.extinction*dt),w=tr*op,illum=material.albedo*(material.ambient+(1-material.ambient)*shadow(px,py,pz)*phase),heat=material.emission===0?0:clamp(temperature(px,py,pz)/5),emit=heat*heat*material.emission;
 if(capture)moment+=w*t;
 c0+=w*(material.colour[0]*illum+emit);c1+=w*(material.colour[1]*illum+emit*.30);c2+=w*(material.colour[2]*illum+emit*.045);tr*=1-op;
 }}if(capture){const i=pix/4,j=i*3,alpha=1-tr,depth=alpha>1e-8?moment/alpha:0;layer[pix]=c0;layer[pix+1]=c1;layer[pix+2]=c2;layer[pix+3]=alpha;
  points[j]=eye[0]+d[0]*depth;points[j+1]=eye[1]+d[1]*depth;points[j+2]=eye[2]+d[2]*depth;
  bgLinear[j]=bg[0];bgLinear[j+1]=bg[1];bgLinear[j+2]=bg[2];}
 out[pix++]=srgb(c0+tr*bg[0]);out[pix++]=srgb(c1+tr*bg[1]);out[pix++]=srgb(c2+tr*bg[2]);out[pix++]=255;
 }if(!capture)return out;
 // Keep the buffers private; copying the public image cannot mutate history.
 const frame=Object.freeze({width,height,get rgba(){return out.slice();}});
 temporalFrames.set(frame,{width,height,rgba:out,layer,points,bgLinear,camera:{eye:eye.slice(),f,r,u,aspect,half,background},extent:extent.slice(),cellSize:extent.map((e,i)=>e/cells[i]),snapshotIdentity});return frame;
 }
 function render(options){return renderInternal(options,false);}
 // Eye/target may be in world space when volumeOrigin is supplied. The existing
 // renderer has an axis-aligned volume and local ground plane. Only translation
 // is supported, not a rotated/scaled world transform.
 function renderFrame({volumeOrigin=[0,0,0],...options}={}){if(!validVector(volumeOrigin)||!validVector(options.eye)||!validVector(options.target))throw new RangeError('invalid temporal camera/origin');return renderInternal({...options,eye:sub(options.eye,volumeOrigin),target:sub(options.target,volumeOrigin)},true);}
 return Object.freeze({render,renderFrame, // Expose only a scalar diagnostic, not the mutable cache.
   transmittanceAt(position){if(!validVector(position)||position.some(x=>x<0||x>1))throw new RangeError('normalized position expected');return shadow(...position);}});
}
/** One-shot convenience wrapper, unchanged public signature. */
export function renderVolume(options){return prepareVolume(options).render(options);}
/** Stable-state temporal AA only. Reset on camera, atlas or material change via identity key. */
export class TemporalPreview {
 constructor(maxFrames=8){if(!Number.isInteger(maxFrames)||maxFrames<1||maxFrames>64)throw new RangeError('invalid history limit');this.maxFrames=maxFrames;this.reset();}
 reset(){this.key=null;this.sum=null;this.frames=0;}
 accumulate(key,rgba){if(typeof key!=='string'||!(rgba instanceof Uint8Array)||rgba.length%4)throw new TypeError('invalid history frame');if(this.key!==key||this.sum?.length!==rgba.length){this.reset();this.key=key;this.sum=new Float32Array(rgba.length);}const weight=1/Math.min(this.frames+1,this.maxFrames);const out=new Uint8Array(rgba.length);for(let i=0;i<rgba.length;i++){if(i%4===3){out[i]=255;continue;}this.sum[i]+=(linear(rgba[i])-this.sum[i])*weight;out[i]=srgb(this.sum[i]);}this.frames=Math.min(this.frames+1,this.maxFrames);return out;}
}

/** Reference temporal reprojection for a single immutable volume snapshot.
 * Current-frame visibility always wins. Never reproject the opaque background.
 * Translation/camera motion is handled in volume-local coordinates. A new
 * prepareVolume() snapshot (density, temperature, material or light) resets
 * history automatically; no claim of motion vectors for evolving fluid fields.
 */
export class ReprojectedPreview {
 #previous=null;
 #maxFrames;
 constructor(maxFrames=4){if(!Number.isInteger(maxFrames)||maxFrames<1||maxFrames>16)throw new RangeError('invalid reprojection history limit');this.#maxFrames=maxFrames;}
 get maxFrames(){return this.#maxFrames;}
 reset(){this.#previous=null;}
 accumulate(key,frame){
  if(typeof key!=='string'||key.length>4096)throw new TypeError('invalid reprojection identity');
  const cur=temporalFrames.get(frame);if(!cur)throw new TypeError('renderFrame() result required');
  const {width:w,height:h,layer,points,bgLinear,camera,extent,cellSize}=cur,n=w*h;
  const prev=this.#previous;let reason=null;
  if(!prev)reason='initial';else if(prev.key!==key)reason='identity';else if(prev.raw.snapshotIdentity!==cur.snapshotIdentity)reason='snapshot';else if(prev.raw.width!==w||prev.raw.height!==h)reason='resolution';else if(prev.raw.camera.background!==camera.background)reason='background';
  else if(dot(prev.raw.camera.f,camera.f)<Math.cos(35*Math.PI/180)||Math.hypot(...sub(prev.raw.camera.eye,camera.eye))>Math.hypot(...extent)*.5)reason='camera-cut';
  else if(this.maxFrames===1)reason='disabled';
  const filtered=layer.slice(),ages=new Float32Array(n),rgba=cur.rgba.slice();
  let visible=0,accepted=0,weightSum=0,maxSamples=0;
  const minAlpha=.005,invCell=cellSize.map(s=>1/s),posTolerance2=1.5**2;
  for(let i=0;i<n;i++){
   const j=i*4,a=layer[j+3],k=i*3;if(a<minAlpha)continue;
   visible++;ages[i]=1;maxSamples=Math.max(maxSamples,1);
   if(reason)continue;
   const raw=prev.raw,pc=raw.camera,dx=points[k]-pc.eye[0],dy=points[k+1]-pc.eye[1],dz=points[k+2]-pc.eye[2];
   const z=dx*pc.f[0]+dy*pc.f[1]+dz*pc.f[2];if(!(z>1e-7))continue;
   const x=((dx*pc.r[0]+dy*pc.r[1]+dz*pc.r[2])/(z*pc.half*pc.aspect)+1)*w*.5-.5;
   const y=(1-(dx*pc.u[0]+dy*pc.u[1]+dz*pc.u[2])/(z*pc.half))*h*.5-.5;
   if(x<0||x>w-1||y<0||y>h-1)continue;
   const ix=Math.floor(x),iy=Math.floor(y),fx=x-ix,fy=y-iy;
   let support=0,historyAge=0,c0=0,c1=0,c2=0,ca=0;
   // Bilinear gather: validate EACH tap against current raw visibility and
   // representative position, so an unrelated occluded/empty ray cannot leak.
   for(let oy=0;oy<=1;oy++)for(let ox=0;ox<=1;ox++){
    const px=ix+ox,py=iy+oy,weight=(ox?fx:1-fx)*(oy?fy:1-fy);if(weight<=0||px>=w||py>=h)continue;
    const pi=px+py*w,pj=pi*4,pk=pi*3,pa=raw.layer[pj+3];
    if(pa<minAlpha||Math.abs(pa-a)>.035+.22*Math.max(a,pa)||prev.ages[pi]<1)continue;
    const d0=(points[k]-raw.points[pk])*invCell[0],d1=(points[k+1]-raw.points[pk+1])*invCell[1],d2=(points[k+2]-raw.points[pk+2])*invCell[2];if(d0*d0+d1*d1+d2*d2>posTolerance2)continue;
    support+=weight;historyAge+=weight*prev.ages[pi];c0+=weight*prev.filtered[pj];c1+=weight*prev.filtered[pj+1];c2+=weight*prev.filtered[pj+2];ca+=weight*prev.filtered[pj+3];
   }
   if(support<.5)continue;
   // Clip to the current 3×3 optical-layer neighborhood in linear light.
   // No history can invent opacity outside the currently visible region.
   const px=i%w,py=Math.floor(i/w),lo=[Infinity,Infinity,Infinity,Infinity],hi=[-Infinity,-Infinity,-Infinity,-Infinity];
   for(let ny=Math.max(0,py-1);ny<=Math.min(h-1,py+1);ny++)for(let nx=Math.max(0,px-1);nx<=Math.min(w-1,px+1);nx++){
    const q=(nx+ny*w)*4;for(let c=0;c<4;c++){lo[c]=Math.min(lo[c],layer[q+c]);hi[c]=Math.max(hi[c],layer[q+c]);}
   }
   const oldCount=Math.min(this.maxFrames-1,historyAge/support),blend=oldCount/(1+oldCount)*support;
   if(blend<=0)continue;
   const old=[c0/support,c1/support,c2/support,ca/support];for(let c=0;c<4;c++)filtered[j+c]=layer[j+c]+blend*(clamp(old[c],lo[c],hi[c])-layer[j+c]);
   // Compose only against THIS frame's background (ground/sky may have moved).
   const tr=1-clamp(filtered[j+3]);for(let c=0;c<3;c++)rgba[j+c]=srgb(filtered[j+c]+tr*bgLinear[k+c]);
   ages[i]=1+oldCount*support;accepted++;weightSum+=blend;maxSamples=Math.max(maxSamples,ages[i]);
  }
  // Only one frame of raw+filtered history is retained, not a growing queue.
  this.#previous={key,raw:cur,filtered,ages};
  return {rgba,diagnostics:Object.freeze({resetReason:reason,visiblePixels:visible,acceptedPixels:accepted,rejectedPixels:visible-accepted,historyFraction:visible?accepted/visible:0,meanHistoryWeight:accepted?weightSum/accepted:0,maxHistorySamples:maxSamples})};
 }
}
