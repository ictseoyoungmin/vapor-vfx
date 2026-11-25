/** CPU procedural volume. Mirrors vapor_core::effects; NOT a fluid fallback. */
const clamp=x=>Math.max(0,Math.min(1,x));
const smooth=(a,b,x)=>{const t=clamp((x-a)/(b-a));return t*t*(3-2*t);};
function hash(x,y,z,seed){let h=seed^Math.imul(x&255,0x9e3779b1)^Math.imul(y&255,0x85ebca77)^Math.imul(z&255,0xc2b2ae3d);h^=h>>>16;h=Math.imul(h,0x7feb352d);h^=h>>>15;h=Math.imul(h,0x846ca68b);h^=h>>>16;return (h>>>0)/4294967295;}
function noise(x,y,z,seed){const ix=Math.floor(x),iy=Math.floor(y),iz=Math.floor(z);const fx=smooth(0,1,x-ix),fy=smooth(0,1,y-iy),fz=smooth(0,1,z-iz);let v=0;for(let k=0;k<2;k++)for(let j=0;j<2;j++)for(let i=0;i<2;i++)v+=(i?fx:1-fx)*(j?fy:1-fy)*(k?fz:1-fz)*hash(ix+i,iy+j,iz+k,seed);return v;}
// Each octave covers only scale+2 lattice points per axis, independent of
// voxel count. Cache lattice hashes and per-axis interpolation weights for
// this snapshot. Float64 and the original multiply/add order preserve bytes.
function makeNoise(cells,shift,scale,offset,seed){
 // For small grids the cost of filling a lattice outweighs saved hashes.
 // Retain direct evaluation below the measured crossover, not a new approximation.
 if(cells[0]*cells[1]*cells[2]<16384)return (x,y,z)=>noise(((x+.5)/cells[0]-shift[0])*scale+offset,((y+.5)/cells[1]-shift[1])*scale+offset,((z+.5)/cells[2]-shift[2])*scale+offset,seed);
 const axes=cells.map((n,a)=>{
   const index=new Int32Array(n),weight=new Float64Array(n);
   let lo=Infinity,hi=-Infinity;
   for(let i=0;i<n;i++){
     const q=((i+.5)/n-shift[a])*scale+offset,base=Math.floor(q);
     index[i]=base;weight[i]=smooth(0,1,q-base);lo=Math.min(lo,base);hi=Math.max(hi,base+1);
   }
   for(let i=0;i<n;i++)index[i]-=lo;
   return {index,weight,lo,size:hi-lo+1};
 });
 const [ax,ay,az]=axes,sx=ax.size,sy=ay.size,sz=az.size,stride=sx*sy;
 const table=new Float64Array(stride*sz);
 for(let z=0;z<sz;z++)for(let y=0;y<sy;y++)for(let x=0;x<sx;x++)table[x+sx*y+stride*z]=hash(ax.lo+x,ay.lo+y,az.lo+z,seed);
 return (x,y,z)=>{
   const base=ax.index[x]+sx*ay.index[y]+stride*az.index[z];
   const fx=ax.weight[x],fy=ay.weight[y],fz=az.weight[z];
   const bx=1-fx,by=1-fy,bz=1-fz;
   let v=0;
   v+=bx*by*bz*table[base];v+=fx*by*bz*table[base+1];
   v+=bx*fy*bz*table[base+sx];v+=fx*fy*bz*table[base+sx+1];
   v+=bx*by*fz*table[base+stride];v+=fx*by*fz*table[base+stride+1];
   v+=bx*fy*fz*table[base+stride+sx];v+=fx*fy*fz*table[base+stride+sx+1];
   return v;
 };
}
const lobes=[[.24,.38,.48,.23,.25,.30],[.43,.48,.51,.25,.38,.31],[.61,.48,.50,.27,.37,.30],[.77,.38,.48,.20,.24,.26],[.43,.66,.48,.18,.26,.22],[.64,.62,.53,.19,.27,.24]];
export function proceduralAtlas(config,kind,settings,time=0){
 if(!['cloud','fog'].includes(kind)||!Number.isFinite(time)||time<0||time>1e7)throw new RangeError('invalid procedural kind/time (0..10000000 s)');
 const cells=config.cells;if(!Array.isArray(cells)||cells.length!==3||cells.some(n=>!Number.isInteger(n)||n<4||n>192)||cells.reduce((a,n)=>a*(n+1),1)>2097152||!Number.isFinite(config.cellSize)||config.cellSize<.001||config.cellSize>10)throw new RangeError('invalid procedural grid');
 const [nx,ny,nz]=cells,extent=cells.map(n=>Math.fround(n*Math.fround(config.cellSize)));
 const {seed}=settings;if(!Number.isInteger(seed)||seed<0||seed>0xffffffff)throw new RangeError('seed must be uint32');
 for(const k of ['coverage','humidity','erosion'])if(!Number.isFinite(settings[k])||settings[k]<0||settings[k]>1)throw new RangeError('invalid '+k);
 const {coverage,humidity,erosion}=Object.fromEntries(['coverage','humidity','erosion'].map(k=>[k,Math.fround(settings[k])]));
 if(!Array.isArray(settings.wind)||settings.wind.length!==3||settings.wind.some((v,i)=>!Number.isFinite(v)||Math.abs(v)>100||Math.abs(v)/extent[i]>100))throw new RangeError('invalid procedural wind');
 const shift=settings.wind.map((v,i)=>((Math.fround(v)*time/extent[i])%256+256)%256);const saturation=(humidity-.5)*.45+(coverage-.5)*.65;
 const noise1=makeNoise(cells,shift,6,0,seed),noise2=makeNoise(cells,shift,15,13,(seed+17)>>>0),noise3=makeNoise(cells,shift,33,-7,(seed+31)>>>0);
 const out=new Uint8Array(nx*ny*nz*4);let o=0;
 for(let z=0;z<nz;z++)for(let y=0;y<ny;y++)for(let x=0;x<nx;x++){
   const px=(x+.5)/nx,py=(y+.5)/ny,pz=(z+.5)/nz;
   const n1=noise1(x,y,z),n2=noise2(x,y,z),n3=noise3(x,y,z);
   const n=.57*n1+.29*n2+.14*n3;let env=0;
   if(kind==='cloud'){let sdf=-10;for(const l of lobes)sdf=Math.max(sdf,1-Math.sqrt(((px-l[0])/l[3])**2+((py-l[1])/l[4])**2+((pz-l[2])/l[5])**2));env=smooth(-.035,.36,sdf+(n1-.5)*.60+(n2-.5)*.37+(n3-.5)*.22);env*=smooth(.12,.25,py)*(1-smooth(.88,1,py));}
   else {const radial=Math.hypot((px-.5)/.56,(pz-.5)/.56);const mask=1-smooth(.58,1.12,radial+(n1-.5)*.4);env=Math.exp(-py*(3.5+4*n2))*(1-smooth(.6,1,py))*mask*(.35+.85*n1+.30*n2);}
   const edge=smooth(0,.10,px)*(1-smooth(.90,1,px))*smooth(0,.10,pz)*(1-smooth(.90,1,pz));
   const rho=clamp(env*(.52+.95*n)+saturation-(.20+(1-n3)*erosion));
   out[o]=Math.round(rho*edge*(kind==='cloud'?Math.sqrt(env):Math.sqrt(clamp(env)))*255);out[o+3]=255;o+=4;
 }return out;
}
