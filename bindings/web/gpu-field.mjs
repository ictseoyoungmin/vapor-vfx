/** Upload a real Float32 scalar field (Rust WASM or explicitly provided baked/reference data).
 * Not a fluid simulation. The source owns one GPU storage buffer, never the device.
 * Density and temperature stay Float32; no RGBA8 quantization. */
const MAX=2097152;
const finite=(v,a,b,n)=>{if(typeof v!=='number'||!Number.isFinite(v)||v<a||v>b)throw new RangeError(`invalid ${n}`);return v;};
const vec=(a,lo,hi,n)=>{if(!a||a.length!==3)throw new RangeError(`invalid ${n}`);return Object.freeze(Array.from(a,x=>finite(x,lo,hi,n)));};
export function packFloatField(volume){
 const cells=vec(volume?.cells,4,512,'cells'),extent=vec(volume.extent,.0001,1e7,'extent');if(!cells.every(Number.isInteger))throw new RangeError('nonintegral cells');
 const count=cells.reduce((a,b)=>a*b,1);if(count>MAX)throw new RangeError('voxel budget exceeded');const cap=finite(volume.densityCap,.00001,100,'density cap');
 const {density,temperature}=volume.fields??{};if(!(density instanceof Float32Array)||!(temperature instanceof Float32Array)||density.length!==count||temperature.length!==count)throw new RangeError('invalid Float32 scalar fields');
 const packed=new Float32Array(count*4);for(let i=0;i<count;i++){packed[i*4]=finite(density[i],0,cap*(1+1e-6),'density');packed[i*4+1]=finite(temperature[i],0,1e5,'temperature');}
 return {packed,cells,extent,densityCap:cap};
}
export class GpuFieldVolume {
 static async create(device,volume,{origin=[0,0,0],reuseBuffers=false}={}){
  const s=new GpuFieldVolume(device,origin,reuseBuffers);try{await s.replace(volume);return s;}catch(e){s.dispose();throw e;}
 }
 constructor(device,origin,reuseBuffers=false){if(!device||!device.queue||!device.limits)throw new TypeError('host-owned WebGPU device required');this.device=device;this.origin=vec(origin,-1e7,1e7,'origin');this.epoch=Object.freeze({});this.tick=0;this.closed=false;this.busy=false;this.buffer=null;this.spare=null;this.reuseBuffers=reuseBuffers===true;this.sourceModel=null;}
 async replace(volume){
  if(this.closed||this.busy)throw new Error('field disposed or upload already pending');this.busy=true;let next=null;
  try{const v=packFloatField(volume);const size=v.packed.byteLength;if(size>Math.min(this.device.limits.maxBufferSize,this.device.limits.maxStorageBufferBindingSize))throw new RangeError('device storage buffer limit exceeded');
   // A replacement never exposes partial data. Prior committed buffer remains usable until successful upload validation.
   this.device.pushErrorScope('validation');let error;try{if(this.spare?.size===size){next=this.spare;this.spare=null;}else{this.spare?.destroy();this.spare=null;next=this.device.createBuffer({label:'vapor-float-field',size,usage:GPUBufferUsage.STORAGE|GPUBufferUsage.COPY_DST});}this.device.queue.writeBuffer(next,0,v.packed);}catch(e){error=e;}
   const scope=await this.device.popErrorScope();if(error)throw error;if(scope)throw new Error(`WebGPU upload: ${scope.message}`);if(this.closed)throw new Error('field disposed during upload');
   const prev=this.buffer;this.buffer=next;next=null;this.cells=v.cells;this.extent=v.extent;this.densityCap=v.densityCap;this.sourceModel=typeof volume.model==='string'?volume.model:'external-float32';this.epoch=Object.freeze({});this.tick=0;if(this.reuseBuffers&&prev?.size===size){this.spare=prev;}else prev?.destroy();return this;
  }finally{next?.destroy();this.busy=false;}
 }
 setOrigin(origin){if(this.closed)throw new Error('field disposed');this.origin=vec(origin,-1e7,1e7,'origin');}
 renderSource(){if(this.closed||!this.buffer)throw new Error('field unavailable');return Object.freeze({device:this.device,buffer:this.buffer,layout:'detail',cells:this.cells,extent:this.extent,origin:this.origin,epoch:this.epoch,tick:this.tick});}
 get bytes(){return (this.buffer?.size??0)+(this.spare?.size??0);}
 dispose(){if(this.closed)return;this.closed=true;this.buffer?.destroy();this.spare?.destroy();this.buffer=null;this.spare=null;}
}
