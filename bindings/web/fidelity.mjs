/** High fidelity CPU reference path. All density is a real Float32 3D field.
 * Independent of the existing procedural atlas and native fluid backends. */
import { getPreset } from './effects.mjs';
const sat=x=>Math.max(0,Math.min(1,x));
const lerp=(a,b,t)=>a+(b-a)*t;
const smooth=(a,b,x)=>{const t=sat((x-a)/(b-a));return t*t*(3-2*t);};
const quintic=t=>t*t*t*(t*(t*6-15)+10);
const fract=x=>x-Math.floor(x);
const v3=(v,name)=>{if(!v||v.length!==3||!Array.from(v).every(Number.isFinite))throw new RangeError('invalid '+name);return Array.from(v);};
const number=(v,a,b,name)=>{if(!Number.isFinite(v)||v<a||v>b)throw new RangeError('invalid '+name);return v;};
const integer=(v,a,b,name)=>{number(v,a,b,name);if(!Number.isInteger(v))throw new RangeError('invalid '+name);return v;};
const dot=(a,b)=>a[0]*b[0]+a[1]*b[1]+a[2]*b[2];
const norm=v=>{const s=Math.hypot(...v);if(!Number.isFinite(s)||!(s>1e-9))throw new RangeError('degenerate vector');return v.map(x=>x/s);};
const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
const sub=(a,b)=>a.map((x,i)=>x-b[i]);
const MAX_VOXELS=2_097_152;
const BRICK=8;
function gridInfo(cells,extent){cells=v3(cells,'cells');extent=v3(extent,'extent');cells.forEach(n=>integer(n,4,512,'cells'));extent.forEach(n=>number(n,.0001,1e7,'extent'));const count=cells.reduce((a,b)=>a*b,1);if(count>MAX_VOXELS)throw new RangeError('volume budget exceeded');return {cells,extent,count};}
function hash(x,y,z,s){let h=(s^Math.imul(x,0x9e3779b1)^Math.imul(y,0x85ebca77)^Math.imul(z,0xc2b2ae3d))>>>0;h=Math.imul(h^(h>>>16),0x7feb352d);h=Math.imul(h^(h>>>15),0x846ca68b);return (h^(h>>>16))>>>0;}
const rand=(x,y,z,s)=>hash(x,y,z,s)/4294967296;
const grad=(h,x,y,z)=>{h&=15;const u=h<8?x:y,v=h<4?y:h===12||h===14?x:z;return (h&1?-u:u)+(h&2?-v:v);};
// Periodic gradient Perlin noise. Periodicity is only for continuous wind advection.
function perlin(x,y,z,s,p){const ix=Math.floor(x),iy=Math.floor(y),iz=Math.floor(z),fx=x-ix,fy=y-iy,fz=z-iz;const u=quintic(fx),v=quintic(fy),w=quintic(fz);const wrap=i=>((i%p)+p)%p;const h=(a,b,c)=>grad(hash(wrap(ix+a),wrap(iy+b),wrap(iz+c),s),fx-a,fy-b,fz-c);return sat(.5+.5*lerp(lerp(lerp(h(0,0,0),h(1,0,0),u),lerp(h(0,1,0),h(1,1,0),u),v),lerp(lerp(h(0,0,1),h(1,0,1),u),lerp(h(0,1,1),h(1,1,1),u),v),w));}
function worley(x,y,z,s,p){const ix=Math.floor(x),iy=Math.floor(y),iz=Math.floor(z);let d=Infinity;for(let k=-1;k<=1;k++)for(let j=-1;j<=1;j++)for(let i=-1;i<=1;i++){const a=ix+i,b=iy+j,c=iz+k;const h=hash((a%p+p)%p,(b%p+p)%p,(c%p+p)%p,s);const dx=a+.08+.84*(h&1023)/1023-x,dy=b+.08+.84*((h>>>10)&1023)/1023-y,dz=c+.08+.84*((h>>>20)&1023)/1023-z;d=Math.min(d,dx*dx+dy*dy+dz*dz);}return 1-sat(Math.sqrt(d)/1.12);}
// Build compact periodic noise tiles, not screen-space noise or a texture overlay.
// All octaves sample actual 3D continuous coordinates. Bounded cache: 2 seeds.
const noiseCache=new Map();
function noiseTiles(seed){if(noiseCache.has(seed)){const t=noiseCache.get(seed);noiseCache.delete(seed);noiseCache.set(seed,t);return t;}const n=40,p=5,a=new Float32Array(n**3),b=new Float32Array(n**3);for(let z=0,i=0;z<n;z++)for(let y=0;y<n;y++)for(let x=0;x<n;x++,i++){a[i]=perlin(x*p/n,y*p/n,z*p/n,seed,p);b[i]=worley(x*p/n,y*p/n,z*p/n,seed^0x45b9f1,p);}const sample=field=>(x,y,z)=>{x=fract(x/p)*n;y=fract(y/p)*n;z=fract(z/p)*n;const i=Math.floor(x),j=Math.floor(y),k=Math.floor(z),u=x-i,v=y-j,w=z-k;const l=i+((j+k*n)*n),l1=(i+1)%n+((j+k*n)*n),m=i+(((j+1)%n+k*n)*n),m1=(i+1)%n+(((j+1)%n+k*n)*n),o=i+((j+(k+1)%n*n)*n),o1=(i+1)%n+((j+(k+1)%n*n)*n),q=i+(((j+1)%n+(k+1)%n*n)*n),q1=(i+1)%n+(((j+1)%n+(k+1)%n*n)*n);return lerp(lerp(lerp(field[l],field[l1],u),lerp(field[m],field[m1],u),v),lerp(lerp(field[o],field[o1],u),lerp(field[q],field[q1],u),v),w);};const t={p:sample(a),w:sample(b)};if(noiseCache.size>=2)noiseCache.delete(noiseCache.keys().next().value);noiseCache.set(seed,t);return t;}
function scalarSampler(field,cells){const [nx,ny,nz]=cells,row=nx,plane=nx*ny;return (x,y,z)=>{if(x<0||y<0||z<0||x>1||y>1||z>1)return 0;const a=Math.max(0,Math.min(nx-1,x*nx-.5)),b=Math.max(0,Math.min(ny-1,y*ny-.5)),c=Math.max(0,Math.min(nz-1,z*nz-.5)),i=Math.floor(a),j=Math.floor(b),k=Math.floor(c),u=a-i,v=b-j,w=c-k,base=i+j*row+k*plane,dx=i<nx-1?1:0,dy=j<ny-1?row:0,dz=k<nz-1?plane:0;return lerp(lerp(lerp(field[base],field[base+dx],u),lerp(field[base+dy],field[base+dy+dx],u),v),lerp(lerp(field[base+dz],field[base+dz+dx],u),lerp(field[base+dz+dy],field[base+dz+dy+dx],u),v),w);};}
function terrainSampler(terrain,cells,extent){if(terrain===undefined)return ()=>0;const [nx,,nz]=cells;if(!(terrain instanceof Float32Array)||terrain.length!==nx*nz||!terrain.every(v=>Number.isFinite(v)&&v>=0&&v<extent[1]))throw new RangeError('terrain must be x-fastest world heights below volume top');return (x,z)=>{const a=Math.max(0,Math.min(nx-1,x*nx-.5)),b=Math.max(0,Math.min(nz-1,z*nz-.5)),i=Math.floor(a),j=Math.floor(b),u=a-i,v=b-j,k=i+j*nx,di=i<nx-1?1:0,dj=j<nz-1?nx:0;return lerp(lerp(terrain[k],terrain[k+di],u),lerp(terrain[k+dj],terrain[k+dj+di],u),v);};}
/** Material and lighting defaults for the opt-in high-fidelity reference renderer.
 * Existing portable presets are not modified. Fluid density is never substituted. */
export function getFidelityPreset(key,quality='high'){
 const p=getPreset(key,quality),material={...p.material,colour:[...p.material.colour]};
 const lighting={light:{direction:[-.80,.56,.16],radiance:[2.6,2.45,2.2]},sky:[.07,.105,.18],ground:[.035,.04,.05],multiScatter:.29};
 if(p.kind==='cloud'){material.extinction=.32;material.ambient=.10;}
 else if(p.kind==='fog'){lighting.sky=[.15,.20,.28];lighting.ground=[.035,.045,.04];lighting.multiScatter=.23;}
 else {lighting.sky=[.05,.07,.10];lighting.ground=[.02,.02,.02];lighting.multiScatter=.20;}
 return {material,lighting};
}
/** New generator: seeded hierarchical thermal columns + warped Perlin/Worley erosion;
 * ground fog follows terrain, with advected anisotropic density bands. Not CFD/weather. */
export function generateFidelityVolume(key,{quality='high',cells,extent,settings={},time=0,terrain}={}){
 const preset=getPreset(key,quality);if(preset.kind==='fluid')throw new RangeError('fluid effects require actual simulation fields');
 extent=extent??preset.config.cells.map(n=>n*preset.config.cellSize);cells=cells??preset.config.cells;
 const g=gridInfo(cells,extent),[nx,ny,nz]=g.cells;extent=g.extent;
 const opts={...preset.procedural,...settings};for(const k of Object.keys(opts))if(!['seed','coverage','humidity','erosion','wind'].includes(k))throw new RangeError('unknown density setting '+k);
 const seed=integer(opts.seed,0,0xffffffff,'seed'),coverage=number(opts.coverage,0,1,'coverage'),humidity=number(opts.humidity,0,1,'humidity'),erosion=number(opts.erosion,0,1,'erosion'),wind=v3(opts.wind,'wind');wind.forEach(v=>number(v,-100,100,'wind'));number(time,0,1e7,'time');
 const t=noiseTiles(seed),p=t.p,w=t.w,shift=wind.map((v,i)=>(v*time/extent[i])%5),density=new Float32Array(g.count),temperature=new Float32Array(g.count),terrainAt=terrainSampler(terrain,g.cells,extent),cloud=preset.kind==='cloud';
 if(cloud&&terrain!==undefined)throw new RangeError('terrain is only supported for ground volumes');
 // One weather system controls the column spacing, width and height; no fixed list of six lobes.
 // Seeded primary thermals are connected by a lower, broader moisture layer.
 const thermals=[];if(cloud){for(let i=0;i<8;i++){const u=i/7,px=.17+.66*u+(rand(i,1,0,seed)-.5)*.055,pz=.5+(rand(i,2,0,seed)-.5)*.24;const core=Math.max(.60*Math.exp(-(((u-.23)/.22)**2)),Math.exp(-(((u-.62)/.26)**2)));const h=.29+.49*core+.13*rand(i,3,0,seed);const rx=.105+.070*rand(i,4,0,seed),rz=.16+.12*rand(i,5,0,seed);thermals.push([px,pz,h,rx,rz]);}}
 let index=0;
 for(let z=0;z<nz;z++)for(let y=0;y<ny;y++)for(let x=0;x<nx;x++,index++){
  const X=(x+.5)/nx,Y=(y+.5)/ny,Z=(z+.5)/nz,xx=X-shift[0],yy=Y-shift[1],zz=Z-shift[2];
  if(cloud){
   const low=p(xx*4.2+2.7,yy*2.8+.2,zz*4.2+1.1),wx=X+.055*(p(xx*5+1,yy*5+2,zz*5)-.5),wz=Z+.070*(p(xx*4,yy*4-1,zz*4+2)-.5),wy=Y+.045*(low-.5);
   let shape=-1;
   for(const [cx,cz,h,rx,rz] of thermals){const base=.16,half=(h-base)*.5,center=base+half;const d=Math.sqrt(((wx-cx)/rx)**2+((wy-center)/half)**2+((wz-cz)/rz)**2);shape=Math.max(shape,(1-d)*Math.min(rx,half,rz)*5);}
   const skirt=1-Math.sqrt(((wx-.5)/.43)**2+((wy-.27)/.15)**2+((wz-.5)/.35)**2);shape=Math.max(shape,skirt*.65);
   if(shape<-.38)continue;
   // Large cellular billows, smaller scallops, and fine surface erosion. Detail
   // erodes the interface rather than modulating opaque interiors uniformly.
   const a=w(xx*9.2,yy*5.4,zz*7.2),b=w(xx*18.4+1.8,yy*10.8+.4,zz*14.4+1.1),c=w(xx*38+2.6,yy*23+3.1,zz*29+2.3),d=p(xx*57,yy*36+1,zz*43);
   const billow=.76*(a-.42)+.38*(b-.43)+.20*(c-.43)+.13*(d-.5)+.23*(low-.5);
   const weather=(coverage-.53)*.38+(humidity-.76)*.24;
   const edge=shape+billow+weather-.10*erosion;
   const baseMask=smooth(.125,.17,Y)*(1-smooth(.91,.99,Y));
   const rho=smooth(-.028,.09,edge)*baseMask*(.60+.40*smooth(.12,.52,edge))*(.67+.33*humidity);
   const border=smooth(0,.08,X)*(1-smooth(.92,1,X))*smooth(0,.08,Z)*(1-smooth(.92,1,Z));
   density[index]=sat(rho*border)*preset.config.densityCap;
  }else{
   const h=(Y*extent[1]-terrainAt(X,Z))/extent[1];if(h<=0||h>.65)continue;
   const dust=key==='dust';
   const warpx=xx+.12*(p(xx*4,yy*2,zz*4)-.5),warpz=zz+.10*(p(xx*4+2,yy*3,zz*4+1)-.5);
   const bands=.52*p(warpx*5,yy*11,warpz*5)+.30*w(warpx*10+1,yy*15,warpz*10)+.18*p(warpx*24,yy*30,warpz*24+2);
   const weather=p(xx*2.8,0.7,zz*2.8+1),height=(dust?.19:.12)*(.6+1.25*weather)*(.6+.6*humidity);
   const layer=Math.exp(-h/height)*(1-smooth(height*1.6,height*3.8,h));
   const pockets=smooth(.22,.73,bands+(coverage-.55)*.48+(humidity-.7)*.20-erosion*.1);
   const border=smooth(0,.10,X)*(1-smooth(.90,1,X))*smooth(0,.10,Z)*(1-smooth(.90,1,Z));
   density[index]=sat(layer*pockets*border*smooth(0,.018,h)*(.76+.24*weather))*preset.config.densityCap;
  }
 }
 return {key,cells:g.cells,extent:g.extent,densityCap:preset.config.densityCap,fields:{density,temperature},model:cloud?'thermal-perlin-worley-v1':'terrain-stratified-fbm-v1'};
}
/** Convert old atlas or externally produced native fields into the shared linear field contract. */
export function atlasToFidelityFields(atlas,cells,densityCap){const {count}=gridInfo(cells,[1,1,1]);number(densityCap,0.00001,100,'density cap');if(!(atlas instanceof Uint8Array)||atlas.length!==count*4)throw new RangeError('invalid atlas');const density=new Float32Array(count),temperature=new Float32Array(count);for(let i=0;i<count;i++){density[i]=atlas[i*4]/255*densityCap;temperature[i]=atlas[i*4+1]/255*16;}return {density,temperature};}
const hg=(g,c)=>(1-g*g)/Math.pow(Math.max(1e-5,1+g*g-2*g*c),1.5);
const phase=(g,c)=>.88*hg(g,c)+.12*hg(-g*.38,c); // normalized over sphere / 4π convention
const exit=(p,d)=>d>1e-12?(1-p)/d:d< -1e-12?-p/d:Infinity;
const srgb=x=>Math.round(255*sat(x<=.0031308?12.92*x:1.055*Math.pow(x,1/2.4)-.055));
function display(x,exposure){const v=Math.max(0,x*exposure);return srgb((v*(2.51*v+.03))/(v*(2.43*v+.59)+.14));}
function lightSpec(light){const direction=norm(v3(light?.direction??[-.62,.74,-.24],'sun direction')),radiance=v3(light?.radiance??[2.8,2.55,2.22],'sun radiance');radiance.forEach(x=>number(x,0,50,'radiance'));return {direction,radiance};}
export function cameraFrame({eye,target,width,height,fov=40}){eye=v3(eye,'eye');target=v3(target,'target');integer(width,1,1600,'width');integer(height,1,1600,'height');number(fov,10,110,'fov');const f=norm(sub(target,eye)),up=Math.abs(f[1])>.99?[0,0,1]:[0,1,0],r=norm(cross(f,up)),u=cross(r,f),half=Math.tan(fov*Math.PI/360),aspect=width/height;return {eye,ray(x,y){const a=(2*(x+.5)/width-1)*half*aspect,b=(1-2*(y+.5)/height)*half;return norm([f[0]+a*r[0]+b*u[0],f[1]+a*r[1]+b*u[1],f[2]+a*r[2]+b*u[2]]);}};}
function skyRadiance(d,sun,background){if(background==='dark')return [.004,.006,.010];const horizon=Math.pow(1-sat(d[1]*1.6),3),sunCos=dot(d,sun.direction),glow=Math.pow(Math.max(0,sunCos),24)*.14;return [lerp(.035,.15,horizon)+glow,lerp(.105,.27,horizon)+glow*.83,lerp(.34,.48,horizon)+glow*.55];}
/** Separate optical depth, sky visibility, low-order scattering and linear HDR composite.
 * Multiple scattering is a bounded empirical transport approximation, NOT a path tracer.
 * All quantities are camera-independent until render(); caches can be reused. */
export function prepareFidelityVolume({fields,cells,extent,densityCap,material,light,sky=[.38,.51,.76],ground=[.12,.10,.075],multiScatter=.48,shadowSteps=24,lightScale=.5,localLight,sunVisibility}={}){
 const g=gridInfo(cells,extent);cells=g.cells;extent=g.extent;number(densityCap,.00001,100,'density cap');
 if(!(fields?.density instanceof Float32Array)||!(fields?.temperature instanceof Float32Array)||fields.density.length!==g.count||fields.temperature.length!==g.count)throw new RangeError('invalid Float32 fields');
 const density=fields.density.slice(),temperature=fields.temperature.slice();const m={...material,colour:v3(material?.colour,'colour')};m.colour.forEach(x=>number(x,0,1,'colour'));for(const [k,a,b] of [['extinction',0,1000],['anisotropy',-.9,.9],['albedo',0,1],['emission',0,10],['thermalFade',0,1],['ambient',0,1]])number(m[k],a,b,k);
 for(let i=0;i<g.count;i++){number(density[i],0,densityCap*(1+1e-6),'density');number(temperature[i],0,1e5,'temperature');if(m.thermalFade)density[i]*=1-m.thermalFade*(1-Math.exp(-temperature[i]));}
 const sun=lightSpec(light);sky=v3(sky,'sky');ground=v3(ground,'ground');[...sky,...ground].forEach(x=>number(x,0,50,'environment radiance'));number(multiScatter,0,1,'multiple scatter');integer(shadowSteps,4,64,'shadow steps');number(lightScale,.125,1,'light cache scale');
 const sample=scalarSampler(density,cells),heat=scalarSampler(temperature,cells),lc=cells.map(n=>Math.max(4,Math.ceil(n*lightScale))),[lx,ly,lz]=lc,ln=lx*ly*lz;
 if(ln*shadowSteps*(localLight?2:1)>64e6)throw new RangeError('light work budget exceeded');
 if(sunVisibility!==undefined&&typeof sunVisibility!=='function')throw new TypeError('sunVisibility must be a function');
 const optical=new Float32Array(ln),upDepth=new Float32Array(ln),downDepth=new Float32Array(ln),localDepth=localLight?new Float32Array(ln):null,visibility=sunVisibility?new Float32Array(ln):null;
 let lamp=null;if(localLight){lamp={position:v3(localLight.position,'light position'),radiance:v3(localLight.radiance,'light radiance'),range:number(localLight.range,.001,1e7,'range'),direction:localLight.direction===undefined?null:norm(v3(localLight.direction,'light direction')),cone:number(localLight.cone??.85,0,.9999,'cone')};lamp.radiance.forEach(x=>number(x,0,500,'local radiance'));}
 const march=(x,y,z,dx,dy,dz,len)=>{if(!(len>0))return 0;const step=len/shadowSteps;let sum=0;for(let j=0;j<shadowSteps;j++){const t=(j+.5)*step;sum+=sample(x+dx*t,y+dy*t,z+dz*t);}return sum*step*m.extinction;};
 const [sx,sy,sz]=sun.direction.map((v,i)=>v/extent[i]);
 for(let z=0;z<lz;z++)for(let x=0;x<lx;x++){
  let running=0;for(let y=ly-1;y>=0;y--){const i=x+lx*(y+ly*z),X=(x+.5)/lx,Y=(y+.5)/ly,Z=(z+.5)/lz,delta=sample(X,Y,Z)*extent[1]/ly*m.extinction;upDepth[i]=running+.5*delta;running+=delta;optical[i]=march(X,Y,Z,sx,sy,sz,Math.min(exit(X,sx),exit(Y,sy),exit(Z,sz)));
   if(visibility)visibility[i]=number(sunVisibility([X*extent[0],Y*extent[1],Z*extent[2]],sun.direction.slice()),0,1,'sun visibility');
   if(lamp){const p=[X*extent[0],Y*extent[1],Z*extent[2]],v=sub(lamp.position,p),len=Math.hypot(...v);if(len>1e-8){const d=v.map((a,j)=>a/len/extent[j]);localDepth[i]=march(X,Y,Z,...d,Math.min(len,exit(X,d[0]),exit(Y,d[1]),exit(Z,d[2])));}}
  }
  running=0;for(let y=0;y<ly;y++){const i=x+lx*(y+ly*z),delta=sample((x+.5)/lx,(y+.5)/ly,(z+.5)/lz)*extent[1]/ly*m.extinction;downDepth[i]=running+.5*delta;running+=delta;}
 }
 const tau=scalarSampler(optical,lc),up=scalarSampler(upDepth,lc),down=scalarSampler(downDepth,lc),local=localDepth?scalarSampler(localDepth,lc):null,vis=visibility?scalarSampler(visibility,lc):null;
 // Conservative brick occupancy includes a one-cell interpolation halo.
 const bc=cells.map(n=>Math.ceil(n/BRICK)),[bx,by,bz]=bc,occupied=new Uint8Array(bx*by*bz),[nx,ny,nz]=cells;
 for(let k=0;k<bz;k++)for(let j=0;j<by;j++)for(let i=0;i<bx;i++){
   outer:for(let z=Math.max(0,k*BRICK-1);z<Math.min(nz,(k+1)*BRICK+1);z++)for(let y=Math.max(0,j*BRICK-1);y<Math.min(ny,(j+1)*BRICK+1);y++)for(let x=Math.max(0,i*BRICK-1);x<Math.min(nx,(i+1)*BRICK+1);x++)if(density[x+nx*(y+ny*z)]>0){occupied[i+bx*(j+by*k)]=1;break outer;}
 }
 function render({eye,target,width=640,height=400,steps=128,fov=40,background='sky',scene,exposure=1,jitter=.5,skipEmpty=true}={}){
  integer(steps,8,512,'steps');number(exposure,.01,20,'exposure');number(jitter,0,1,'jitter');if(!['sky','dark'].includes(background))throw new RangeError('invalid background');const cam=cameraFrame({eye,target,width,height,fov});const pixels=width*height;if(pixels*steps>180e6)throw new RangeError('render work budget exceeded');
  if(scene!==undefined){if(!(scene.depth instanceof Float32Array)||scene.depth.length!==pixels||!(scene.radiance instanceof Float32Array)||scene.radiance.length!==pixels*3)throw new RangeError('scene requires linear HDR radiance and ray distance');if(!scene.depth.every(x=>Number.isFinite(x)&&x>=0)||!scene.radiance.every(x=>Number.isFinite(x)&&x>=0&&x<=100))throw new RangeError('invalid scene values');}
  if(typeof skipEmpty!=='boolean')throw new TypeError('skipEmpty must be boolean');const rgba=new Uint8Array(pixels*4),alpha=new Float32Array(pixels),linear=new Float32Array(pixels*3);let samples=0,visible=0,skipped=0;
  for(let y=0,i=0;y<height;y++)for(let x=0;x<width;x++,i++){
   const d=cam.ray(x,y);let near=0,far=Infinity;for(let a=0;a<3;a++){if(Math.abs(d[a])<1e-9){if(cam.eye[a]<0||cam.eye[a]>extent[a]){far=-1;break;}}else{const l=-cam.eye[a]/d[a],h=(extent[a]-cam.eye[a])/d[a];near=Math.max(near,Math.min(l,h));far=Math.min(far,Math.max(l,h));}}
   if(scene&&scene.depth[i]>0)far=Math.min(far,scene.depth[i]);const bg=scene?scene.radiance.subarray(i*3,i*3+3):skyRadiance(d,sun,background);let trans=1,c0=0,c1=0,c2=0;
   const cos=dot(d,sun.direction),p1=phase(m.anisotropy,cos),p2=phase(m.anisotropy*.43,cos),p3=phase(m.anisotropy*.15,cos);
   if(far>near){const dt=(far-near)/steps;for(let j=0;j<steps&&trans>.0007;j++){
    const t=near+(j+jitter)*dt,X=(cam.eye[0]+d[0]*t)/extent[0],Y=(cam.eye[1]+d[1]*t)/extent[1],Z=(cam.eye[2]+d[2]*t)/extent[2];
    if(skipEmpty&&X>=0&&Y>=0&&Z>=0&&X<=1&&Y<=1&&Z<=1){const a=Math.min(bx-1,Math.floor(X*nx/BRICK)),b=Math.min(by-1,Math.floor(Y*ny/BRICK)),c=Math.min(bz-1,Math.floor(Z*nz/BRICK));if(!occupied[a+bx*(b+by*c)]){
      const jumpAxis=(P,dir,dim,brick,size)=>Math.abs(dir)<1e-12?Infinity:((dir>0?Math.min(dim,(brick+1)*BRICK):brick*BRICK)/dim-P)*size/dir;
      const distance=Math.min(jumpAxis(X,d[0],nx,a,extent[0]),jumpAxis(Y,d[1],ny,b,extent[1]),jumpAxis(Z,d[2],nz,c,extent[2]));
      const jump=Math.max(1,Math.min(steps-j,Math.ceil(distance/dt-1e-8)));skipped+=jump;j+=jump-1;continue;}}
    const rho=sample(X,Y,Z);samples++;if(rho<=1e-7)continue;
    const opacity=-Math.expm1(-rho*m.extinction*dt),weight=trans*opacity,od=tau(X,Y,Z),ou=up(X,Y,Z),og=down(X,Y,Z);
    // First order sunlight, then two broader/less attenuated lobes. Their
    // weights decay with scattering albedo; no fake surface normal shading.
    const visibleSun=vis?vis(X,Y,Z):1,direct=visibleSun*Math.exp(-od)*p1,scattered=(.35+.65*visibleSun)*multiScatter*(.50*m.albedo*Math.exp(-.33*od)*p2+.23*m.albedo*m.albedo*Math.exp(-.10*od)*p3);
    const skyVis=.20*Math.exp(-.09*ou)+.80*Math.exp(-.65*ou),groundVis=Math.exp(-.23*og),env=m.ambient* .30;
    let l0=sun.radiance[0]*(direct+scattered)+sky[0]*(skyVis+env)+ground[0]*groundVis,l1=sun.radiance[1]*(direct+scattered)+sky[1]*(skyVis+env)+ground[1]*groundVis,l2=sun.radiance[2]*(direct+scattered)+sky[2]*(skyVis+env)+ground[2]*groundVis;
    if(lamp){const dx=lamp.position[0]-X*extent[0],dy=lamp.position[1]-Y*extent[1],dz=lamp.position[2]-Z*extent[2],distance=Math.hypot(dx,dy,dz),range=sat(1-distance/lamp.range);if(range>0&&distance>1e-6){const lx=dx/distance,ly=dy/distance,lz=dz/distance,spot=lamp.direction?smooth(lamp.cone,Math.min(.9999,lamp.cone+.07),-(lx*lamp.direction[0]+ly*lamp.direction[1]+lz*lamp.direction[2])):1,atten=range*range/(1+6*(distance/lamp.range)**2)*spot*Math.exp(-local(X,Y,Z))*phase(m.anisotropy,d[0]*lx+d[1]*ly+d[2]*lz);l0+=lamp.radiance[0]*atten;l1+=lamp.radiance[1]*atten;l2+=lamp.radiance[2]*atten;}}
    const e=m.emission?sat(heat(X,Y,Z)/5)**2*m.emission:0;c0+=weight*(m.colour[0]*m.albedo*l0+e);c1+=weight*(m.colour[1]*m.albedo*l1+e*.30);c2+=weight*(m.colour[2]*m.albedo*l2+e*.045);trans*=1-opacity;
   }}alpha[i]=1-trans;visible+=alpha[i]>.001;const k=i*3,q=i*4;linear[k]=c0+trans*bg[0];linear[k+1]=c1+trans*bg[1];linear[k+2]=c2+trans*bg[2];rgba[q]=display(linear[k],exposure);rgba[q+1]=display(linear[k+1],exposure);rgba[q+2]=display(linear[k+2],exposure);rgba[q+3]=255;
  }
  return {rgba,alpha,linear,diagnostics:{visiblePixels:visible,samples,skippedSamples:skipped,occupiedBricks:occupied.reduce((a,b)=>a+b,0),totalBricks:occupied.length,lightCells:lc.slice(),cacheBytes:ln*4*(3+Number(!!lamp)+Number(!!visibility))+occupied.length,reference:true}};
 }
 return Object.freeze({render,transmittanceAt(position){const p=v3(position,'normalized position');if(p.some(x=>x<0||x>1))throw new RangeError('invalid position');return Math.exp(-tau(...p));}});
}
