/** Rust WASM binding. No JavaScript solver and no silent substitute on missing WASM. */
const STATUS={[-1]:'invalid argument or ABI mismatch',[-2]:'invalid/released handle',[-3]:'buffer too small',[-4]:'resource limit',[-5]:'non-finite state; reset required',[-6]:'internal failure'};
export class VaporError extends Error {constructor(code,message=STATUS[code]??'unknown error'){super(`Vapor [${code}]: ${message}`);this.name='VaporError';this.code=code;}}
export const Fields=Object.freeze({density:0,temperature:1,pressure:2,solid:3,velocity:4});
const configSchema={nx:[8,'u'],ny:[12,'u'],nz:[16,'u'],cellSize:[20,'f'],origin:[24,'v'],fixedDt:[36,'f'],maxSubsteps:[40,'u'],pressureIterations:[44,'u'],sorOmega:[48,'f'],densityDecay:[52,'f'],cooling:[56,'f'],buoyancy:[60,'f'],densityWeight:[64,'f'],drag:[68,'f'],vorticity:[72,'f'],wind:[76,'v'],maxVelocity:[88,'f'],densityCap:[92,'f'],boundary:[96,'u']};
const emitterSchema={position:[8,'v'],direction:[20,'v'],radius:[32,'f'],length:[36,'f'],speed:[40,'f'],densityRate:[44,'f'],temperature:[48,'f'],enabled:[52,'b']};
const renderSchema={width:[8,'u'],height:[12,'u'],steps:[16,'u'],extinction:[20,'f'],colour:[24,'v'],eye:[36,'v'],target:[48,'v'],up:[60,'v'],verticalFovDegrees:[72,'f']};
const obstacleSchema={kind:[8,'u'],a:[12,'v'],b:[24,'v'],radius:[36,'f'],velocity:[40,'v'],enabled:[52,'b']};
function uint(x,name){if(!Number.isInteger(x)||x<0||x>0xffffffff)throw new RangeError(`${name} must be uint32`);return x;}
function finite(x,name){if(typeof x!=='number'||!Number.isFinite(x))throw new TypeError(`${name} must be finite`);return x;}
function patch(view,p,schema,options){for(const [key,value] of Object.entries(options)){const def=Object.hasOwn(schema,key)?schema[key]:null;if(!def)throw new TypeError(`Unknown option: ${key}`);const [offset,type]=def;if(type==='v'){if(value==null||value.length!==3)throw new TypeError(`${key} must contain 3 numbers`);for(let i=0;i<3;i++)view.setFloat32(p+offset+i*4,finite(value[i],key),true);}else if(type==='u')view.setUint32(p+offset,uint(value,key),true);else if(type==='b'){if(typeof value!=='boolean')throw new TypeError(`${key} must be boolean`);view.setUint32(p+offset,value?1:0,true);}else view.setFloat32(p+offset,finite(value,key),true);}}
function readConfig(v,p){const result={};for(const [key,[off,t]] of Object.entries(configSchema)){result[key]=t==='v'?[0,1,2].map(i=>v.getFloat32(p+off+i*4,true)):t==='u'?v.getUint32(p+off,true):v.getFloat32(p+off,true);}result.cells=Object.freeze([result.nx,result.ny,result.nz]);Object.freeze(result.origin);Object.freeze(result.wind);return Object.freeze(result);}
export class VaporModule {
  constructor(exports){this.e=exports;if(!(exports.memory instanceof WebAssembly.Memory)||typeof exports.vapor_abi_version_v1!=='function'||exports.vapor_abi_version_v1()!==1)throw new VaporError(-1,'WASM ABI mismatch');}
  view(){return new DataView(this.e.memory.buffer);}
  check(code){if(code!==0)throw new VaporError(code);}
  alloc(bytes){const p=this.e.vapor_alloc_v1(uint(bytes,'bytes'))>>>0;if(!p)throw new VaporError(-4);return p;}
  free(p){this.check(this.e.vapor_free_v1(p));}
  temporary(bytes,fn){const p=this.alloc(bytes);try{return fn(p);}finally{this.free(p);}}
  createSimulation(options={}){return new Simulation(this,options);}
}
export async function loadVapor(source=new URL('./vapor.wasm',import.meta.url)){
  let bytes=source;
  if(typeof source==='string'||source instanceof URL){const response=await fetch(source);if(!response.ok)throw new Error(`Cannot load Vapor WASM: HTTP ${response.status}`);bytes=await response.arrayBuffer();}
  const {instance}=await WebAssembly.instantiate(bytes,{});return new VaporModule(instance.exports);
}
export class Simulation {
  #m;#h=0;#cache=new Map();
  constructor(module,options={}){this.#m=module;const opts={...options};if(opts.cells!==undefined){if(opts.cells.length!==3)throw new TypeError('cells must contain 3 integers');[opts.nx,opts.ny,opts.nz]=opts.cells;delete opts.cells;}
    module.temporary(104,p=>{module.check(module.e.vapor_default_config_v1(p,100));patch(module.view(),p,configSchema,opts);Object.defineProperty(this,'config',{value:readConfig(module.view(),p),enumerable:true,writable:false});module.check(module.e.vapor_create_v1(p,p+100));this.#h=module.view().getUint32(p+100,true);});
  }
  get closed(){return this.#h===0;}
  #handle(){if(!this.#h)throw new VaporError(-2);return this.#h;}
  #buffer(key,bytes){if(!this.#cache.has(key))this.#cache.set(key,this.#m.alloc(bytes));return this.#cache.get(key);}
  dispose(){
    if(!this.#h)return;
    const h=this.#h;this.#h=0;let error;
    try{this.#m.check(this.#m.e.vapor_release_v1(h));}catch(e){error=e;}
    // Attempt every free even when one fails. No live handle can escape disposal.
    for(const p of this.#cache.values()){
      try{this.#m.free(p);}catch(e){error??=e;}
    }
    this.#cache.clear();if(error)throw error;
  }
  reset(){this.#m.check(this.#m.e.vapor_reset_v1(this.#handle()));}
  step(steps=1){this.#m.check(this.#m.e.vapor_step_v1(this.#handle(),uint(steps,'steps')));}
  advance(seconds){const h=this.#handle();finite(seconds,'seconds');return this.#m.temporary(40,p=>{this.#m.check(this.#m.e.vapor_advance_v1(h,seconds,p,40));const v=this.#m.view();return {steps:v.getUint32(p+8,true),alpha:v.getFloat64(p+16,true),droppedSeconds:v.getFloat64(p+24,true),simulatedSeconds:v.getFloat64(p+32,true)};});}
  setEmitter(id,options={}){const h=this.#handle();uint(id,'emitter id');this.#m.temporary(56,p=>{this.#m.check(this.#m.e.vapor_default_emitter_v1(p,56));patch(this.#m.view(),p,emitterSchema,options);this.#m.check(this.#m.e.vapor_set_emitter_v1(h,id,p));});}
  removeEmitter(id){this.#m.check(this.#m.e.vapor_remove_emitter_v1(this.#handle(),uint(id,'emitter id')));}
  setCapsule(id,a,b,radius,velocity=[0,0,0]){this.#obstacle(id,{kind:0,a,b,radius,velocity,enabled:true});}
  setSphere(id,center,radius,velocity=[0,0,0]){this.setCapsule(id,center,center,radius,velocity);}
  setBox(id,minimum,maximum,velocity=[0,0,0]){this.#obstacle(id,{kind:1,a:minimum,b:maximum,radius:0,velocity,enabled:true});}
  #obstacle(id,options){const h=this.#handle();uint(id,'obstacle id');this.#m.temporary(56,p=>{const view=this.#m.view();view.setUint32(p,56,true);view.setUint32(p+4,1,true);patch(view,p,obstacleSchema,options);this.#m.check(this.#m.e.vapor_set_obstacle_v1(h,id,p));});}
  removeObstacle(id){this.#m.check(this.#m.e.vapor_remove_obstacle_v1(this.#handle(),uint(id,'obstacle id')));}
  setProfile(id,points,{duration=2,startTime=0,repeat=false}={}){const h=this.#handle();uint(id,'emitter id');finite(duration,'duration');finite(startTime,'startTime');if(typeof repeat!=='boolean')throw new TypeError('repeat must be boolean');if(points==null||points.length===0){this.#m.check(this.#m.e.vapor_set_profile_v1(h,id,0,0,duration,startTime,repeat?1:0));return;}
    if(!Array.isArray(points)||points.length<2||points.length>64||points.some(row=>!Array.isArray(row)||row.length!==4))throw new TypeError('profile requires 2..64 rows [x,speed,amount,density]');
    this.#m.temporary(points.length*32,p=>{const v=this.#m.view();let i=0;for(const row of points)for(const x of row)v.setFloat64(p+8*i++,finite(x,'profile value'),true);this.#m.check(this.#m.e.vapor_set_profile_v1(h,id,p,points.length,duration,startTime,repeat?1:0));});
  }
  metrics(){const h=this.#handle();return this.#m.temporary(112,p=>{this.#m.check(this.#m.e.vapor_metrics_v1(h,p,112));const v=this.#m.view();return {ticks:Number(v.getBigUint64(p+8,true)),time:v.getFloat64(p+16,true),densityIntegral:v.getFloat64(p+24,true),maxDensity:v.getFloat32(p+32,true),maxSpeed:v.getFloat32(p+36,true),divergenceRms:v.getFloat64(p+40,true),pressureResidualRms:v.getFloat64(p+48,true),centroid:[0,1,2].map(i=>v.getFloat64(p+56+i*8,true)),nonFinite:v.getUint32(p+80,true),clampedVelocities:Number(v.getBigUint64(p+88,true)),droppedSeconds:v.getFloat64(p+96,true),cpuBytes:Number(v.getBigUint64(p+104,true))};});}
  field(name='density'){const h=this.#handle();const f=Object.hasOwn(Fields,name)?Fields[name]:undefined;if(f===undefined)throw new TypeError('unknown field');const n=this.config.nx*this.config.ny*this.config.nz*(f===4?3:1);const p=this.#buffer(`field:${f}`,n*4);this.#m.check(this.#m.e.vapor_copy_field_v1(h,f,p,n));return new Float32Array(this.#m.e.memory.buffer,p,n).slice();}
  macCells(){const h=this.#handle();if(typeof this.#m.e.vapor_copy_mac_v1!=='function')throw new VaporError(-9,'Hybrid requires the v0.3 Rust WASM binary');const n=(this.config.nx+1)*(this.config.ny+1)*(this.config.nz+1)*8;const p=this.#buffer('MAC',n*4);this.#m.check(this.#m.e.vapor_copy_mac_v1(h,p,n));return new Float32Array(this.#m.e.memory.buffer,p,n).slice();}
  /** Actual Rust CPU preview. Linear premultiplied RGBA8, not straight-alpha sRGB. */
  renderRGBA8(options={}){
    const h=this.#handle();
    const cfg={width:320,height:240,steps:72,extinction:16,colour:[.85,.9,.95],up:[0,1,0],verticalFovDegrees:45,...options};
    uint(cfg.width,'width');uint(cfg.height,'height');uint(cfg.steps,'steps');
    if(!cfg.width||!cfg.height||cfg.width>4096||cfg.height>4096||cfg.steps<8||cfg.steps>1024||cfg.width*cfg.height*cfg.steps>256000000)throw new RangeError('render dimensions/steps exceed work budget');
    if(!cfg.eye||!cfg.target)throw new TypeError('eye and target are required');
    if(typeof this.#m.e.vapor_render_v1!=='function')throw new VaporError(-9,'Actual Rust preview renderer export is missing');
    // Temporary allocation, not a new persistent cache entry for each resize.
    return this.#m.temporary(76,p=>{
      const v=this.#m.view();v.setUint32(p,76,true);v.setUint32(p+4,1,true);patch(v,p,renderSchema,cfg);
      const n=cfg.width*cfg.height*4;
      return this.#m.temporary(n,out=>{
        this.#m.check(this.#m.e.vapor_render_v1(h,p,out,n));
        // Allocations or the Rust call may grow WASM memory; reacquire the view.
        return new Uint8Array(this.#m.e.memory.buffer,out,n).slice();
      });
    });
  }
  atlasRGBA8(){const h=this.#handle();const n=this.config.nx*this.config.ny*this.config.nz*4;const p=this.#buffer('atlas',n);this.#m.check(this.#m.e.vapor_copy_atlas_v1(h,p,n));return new Uint8Array(this.#m.e.memory.buffer,p,n).slice();}
}
