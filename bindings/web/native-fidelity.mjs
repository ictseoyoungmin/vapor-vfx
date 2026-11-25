/** Native Rust CPU Fidelity via WASM. No reference-generator fallback.
 * Stateless ABI: each call builds its own Rust generator/lighting cache.
 * Intended for offline/authoring/small previews, not a real-time game render loop.
 */
import {VaporError,VaporModule} from './vapor.mjs';
import {getPreset} from './effects.mjs';
const LIMIT=2097152;
const bounded=(x,min,max,label)=>{if(typeof x!=='number'||!Number.isFinite(x)||x<min||x>max)throw new RangeError(`invalid ${label}`);return x;};
const integer=(x,min,max,label)=>{bounded(x,min,max,label);if(!Number.isInteger(x))throw new RangeError(`invalid ${label}`);return x;};
function vec(v,min,max,label){if(!v||v.length!==3)throw new TypeError(`${label} requires 3 values`);return Array.from(v,x=>bounded(x,min,max,label));}
function grid(cells,extent,densityCap){cells=vec(cells,4,512,'cells').map(x=>integer(x,4,512,'cells'));extent=vec(extent,.0001,1e7,'extent');bounded(densityCap,.00001,100,'density cap');const n=cells[0]*cells[1]*cells[2];if(n>LIMIT)throw new RangeError('voxel budget exceeded');return {cells,extent,densityCap,n};}
function floatArray(a,n,label){if(!(a instanceof Float32Array)||a.length!==n)throw new RangeError(`invalid ${label} buffer`);return a;}
function pack(view,p,bytes,fields){new Uint8Array(view.buffer,p,bytes).fill(0);view.setUint32(p,bytes,true);view.setUint32(p+4,1,true);for(const [off,format,val] of fields){const values=Array.isArray(val)?val:[val];values.forEach((v,i)=>format==='u'?view.setUint32(p+off+i*4,v,true):view.setFloat64(p+off+i*8,v,true));}}
function packGrid(v,p,g){pack(v,p,56,[[8,'u',g.cells],[24,'d',g.extent],[48,'d',g.densityCap]]);}
function options(input,defaults){const result={...defaults};for(const [k,v] of Object.entries(input??{})){if(!Object.hasOwn(defaults,k))throw new TypeError(`unknown option ${k}`);result[k]=v;}return result;}
/** Allocate all scratch before acquiring views. Returned arrays are independent copies. */
function scratch(m,sizes,fn){const ptr=[];let result,err;try{for(const n of sizes)ptr.push(n?m.alloc(n):0);result=fn(ptr);}catch(e){err=e;}finally{for(const p of ptr.reverse()){if(p)try{m.free(p);}catch(e){err??=e;}}}if(err)throw err;return result;}
export class NativeFidelityCPU {
 constructor(module){if(!(module instanceof VaporModule))throw new TypeError('expected VaporModule');for(const key of ['vapor_fidelity_generate_v1','vapor_fidelity_render_v1'])if(typeof module.e[key]!=='function')throw new VaporError(-9,'Actual Rust Fidelity WASM exports missing; rebuild SDK');this.module=module;}
 generate(key,{quality='high',cells,extent,settings,time=0,terrain}={}){
  const preset=getPreset(key,quality),kind={cumulus_cloud:1,ground_fog:2,dust:3}[preset.key];if(!kind)throw new RangeError('fluid requires actual simulation fields');
  const g=grid(cells??preset.config.cells,extent??preset.config.cells.map(x=>x*preset.config.cellSize),preset.config.densityCap),s=options(settings,preset.procedural);integer(s.seed,0,0xffffffff,'seed');for(const k of ['coverage','humidity','erosion'])bounded(s[k],0,1,k);s.wind=vec(s.wind,-100,100,'wind');bounded(time,0,1e7,'time');
  const count=terrain===undefined?0:g.cells[0]*g.cells[2];if(terrain!==undefined){if(kind===1)throw new RangeError('cloud does not accept terrain');floatArray(terrain,count,'terrain');}
  const m=this.module;
  return scratch(m,[56,64,count*4,g.n*4,g.n*4],([gp,sp,tp,dp,hp])=>{const v=m.view();packGrid(v,gp,g);pack(v,sp,64,[[8,'u',kind],[12,'u',s.seed],[16,'d',s.coverage],[24,'d',s.humidity],[32,'d',s.erosion],[40,'d',s.wind]]);if(count)new Float32Array(v.buffer,tp,count).set(terrain);m.check(m.e.vapor_fidelity_generate_v1(gp,sp,time,tp,count,dp,hp,g.n));const b=m.e.memory.buffer;return {cells:g.cells,extent:g.extent,densityCap:g.densityCap,fields:{density:new Float32Array(b,dp,g.n).slice(),temperature:new Float32Array(b,hp,g.n).slice()},key:preset.key,model:'rust-wasm-fidelity'};});
 }
 render(volume,camera,settings={}){
  const g=grid(volume.cells,volume.extent,volume.densityCap);const d=floatArray(volume.fields?.density,g.n,'density'),t=floatArray(volume.fields?.temperature,g.n,'temperature');
  const c=options(camera,{eye:null,target:null,width:640,height:400,steps:128,fov:40,exposure:1,jitter:.5,background:'sky',scene:undefined});
  c.eye=vec(c.eye,-1e8,1e8,'eye');c.target=vec(c.target,-1e8,1e8,'target');integer(c.width,1,1600,'width');integer(c.height,1,1600,'height');integer(c.steps,8,512,'steps');const p=c.width*c.height;if(p*c.steps>180000000)throw new RangeError('render budget exceeded');bounded(c.fov,10,110,'fov');bounded(c.exposure,.0001,100,'exposure');bounded(c.jitter,0,1,'jitter');if(!['sky','dark'].includes(c.background))throw new RangeError('invalid background');
  const o=options(settings,{colour:[.91,.96,1],extinction:.32,anisotropy:.55,albedo:.9,emission:0,thermalFade:0,ambient:.1,direction:[-.8,.56,.16],radiance:[2.6,2.45,2.2],sky:[.07,.105,.18],ground:[.035,.04,.05],multiScatter:.29,shadowSteps:24,lightScale:.5});
  for(const k of ['colour','direction','radiance','sky','ground'])o[k]=vec(o[k],k==='direction'?-1e6:0,1e6,k);
  for(const k of ['extinction','albedo','emission','thermalFade','ambient','multiScatter','lightScale'])bounded(o[k],0,1e6,k);bounded(o.anisotropy,-.99,.99,'anisotropy');integer(o.shadowSteps,1,512,'shadowSteps');
  const scene=c.scene;const sc=scene===undefined?0:p;if(sc){floatArray(scene.depth,p,'scene depth');floatArray(scene.radiance,p*3,'scene radiance');}
  const m=this.module;return scratch(m,[56,200,96,g.n*4,g.n*4,sc*4,sc*12,p*4,p*4],([gp,op,cp,dp,tp,zp,rp,out,ap])=>{
   const v=m.view();packGrid(v,gp,g);pack(v,op,200,[[8,'u',o.shadowSteps],[16,'d',o.colour],[40,'d',o.extinction],[48,'d',o.anisotropy],[56,'d',o.albedo],[64,'d',o.emission],[72,'d',o.thermalFade],[80,'d',o.ambient],[88,'d',o.direction],[112,'d',o.radiance],[136,'d',o.sky],[160,'d',o.ground],[184,'d',o.multiScatter],[192,'d',o.lightScale]]);pack(v,cp,96,[[8,'u',c.width],[12,'u',c.height],[16,'u',c.steps],[20,'u',c.background==='dark'?1:0],[24,'d',c.eye],[48,'d',c.target],[72,'d',c.fov],[80,'d',c.exposure],[88,'d',c.jitter]]);
   new Float32Array(v.buffer,dp,g.n).set(d);new Float32Array(v.buffer,tp,g.n).set(t);if(sc){new Float32Array(v.buffer,zp,p).set(scene.depth);new Float32Array(v.buffer,rp,p*3).set(scene.radiance);}
   m.check(m.e.vapor_fidelity_render_v1(gp,op,cp,dp,tp,g.n,zp,rp,sc,out,p*4,ap,p));const b=m.e.memory.buffer;return {rgba:new Uint8Array(b,out,p*4).slice(),alpha:new Float32Array(b,ap,p).slice(),width:c.width,height:c.height,model:'rust-wasm-fidelity'};
  });
 }
}
