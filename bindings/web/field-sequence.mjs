/** VPA1: validated timeline of independently checksummed VPF1 frames.
 * Source callbacks must bound response size. The player holds <=2 decoded keyframes.
 * Scalar interpolation is Eulerian; no motion compensation, no loop by default. */
import {decodeFieldAsset,fieldCRC32} from './field-asset.mjs';
import {GpuFieldVolume} from './gpu-field.mjs';
const HEADER=64, RECORD=16, MAX_FRAMES=4096, MAX_VOXELS=2097152, MAX_INDEX=HEADER+RECORD*MAX_FRAMES;
const bytes=x=>x instanceof ArrayBuffer?new Uint8Array(x):x;
const good=(v,a,b)=>typeof v==='number'&&Number.isFinite(v)&&v>=a&&v<=b;
const same=(a,b)=>a.length===b.length&&a.every((x,i)=>x===b[i]);
export function frameFilename(i){if(!Number.isInteger(i)||i<0||i>=MAX_FRAMES)throw RangeError('invalid VPA frame index');return `frame_${String(i).padStart(4,'0')}.vpf`;}
export function decodeSequenceIndex(input){
 const b=bytes(input);if(!(b instanceof Uint8Array)||b.length<HEADER+RECORD||b.length>MAX_INDEX)throw RangeError('invalid VPA index length');
 const v=new DataView(b.buffer,b.byteOffset,b.byteLength),count=v.getUint32(8,true);
 if(v.getUint32(0,true)!==0x31415056||v.getUint32(4,true)!==HEADER||count<1||count>MAX_FRAMES||b.length!==HEADER+count*RECORD||v.getUint32(28,true)!==0||fieldCRC32(b.subarray(16))!==v.getUint32(12,true))throw RangeError('invalid VPA header/checksum');
 const cells=[16,20,24].map(i=>v.getUint32(i,true)),extent=[32,40,48].map(i=>v.getFloat64(i,true)),densityCap=v.getFloat64(56,true),n=cells.reduce((a,b)=>a*b,1);
 if(!cells.every(x=>Number.isInteger(x)&&good(x,4,512))||n>MAX_VOXELS||!extent.every(x=>good(x,.0001,1e7))||!good(densityCap,.00001,100))throw RangeError('invalid VPA grid');
 const records=[];let last=-1;
 for(let i=0;i<count;i++){const o=HEADER+i*RECORD,time=v.getFloat64(o,true),byteLength=v.getUint32(o+8,true),crc=v.getUint32(o+12,true);if(!good(time,0,1e7)||time<=last||byteLength!==80+n*8)throw RangeError('invalid VPA record');last=time;records.push(Object.freeze({time,byteLength,crc}));}
 return Object.freeze({cells:Object.freeze(cells),extent:Object.freeze(extent),densityCap,records:Object.freeze(records)});
}
export class FieldSequence {
 #load;#cache=new Map();#busy=false;#closed=false;#index;#generation=0;
 constructor(index,loadFrame){if(typeof loadFrame!=='function')throw TypeError('loadFrame required');this.#index=decodeSequenceIndex(index);this.#load=loadFrame;}
 get index(){return this.#index;}get cachedFrames(){return this.#cache.size;}get closed(){return this.#closed;}
 get startTime(){return this.index.records[0].time;}get endTime(){return this.index.records.at(-1).time;}
 async #frame(i,g){
  if(this.#cache.has(i)){const f=this.#cache.get(i);this.#cache.delete(i);this.#cache.set(i,f);return f;}
  const r=this.index.records[i],raw=bytes(await this.#load(i,r.byteLength));
  if(this.#closed||g!==this.#generation)throw Error('sequence request cancelled');
  if(!(raw instanceof Uint8Array)||raw.length!==r.byteLength||fieldCRC32(raw)!==r.crc)throw RangeError('VPA frame length/checksum mismatch');
  const f=decodeFieldAsset(raw),idx=this.index;if(!same(f.cells,idx.cells)||!same(f.extent,idx.extent)||f.densityCap!==idx.densityCap||f.time!==r.time)throw RangeError('VPA frame metadata mismatch');
  if(this.#cache.size===2)this.#cache.delete(this.#cache.keys().next().value);this.#cache.set(i,f);return f;
 }
 async sample(time){
  if(this.#closed||this.#busy)throw Error('sequence disposed or sample pending');if(!Number.isFinite(time))throw RangeError('invalid sample time');
  this.#busy=true;const g=this.#generation;
  try{
   const r=this.index.records;time=Math.min(this.endTime,Math.max(this.startTime,time));let lo=0,hi=r.length-1;while(lo<hi){const mid=Math.ceil((lo+hi)/2);if(r[mid].time<=time)lo=mid;else hi=mid-1;}
   const a=await this.#frame(lo,g);let density,temperature;
   if(time===a.time){density=a.fields.density.slice();temperature=a.fields.temperature.slice();}
   else{const b=await this.#frame(lo+1,g),u=(time-a.time)/(b.time-a.time);const blend=(x,y)=>{const out=new Float32Array(x.length);for(let i=0;i<x.length;i++)out[i]=x[i]+(y[i]-x[i])*u;return out;};density=blend(a.fields.density,b.fields.density);temperature=blend(a.fields.temperature,b.fields.temperature);}
   if(this.#closed||g!==this.#generation)throw Error('sequence request cancelled');
   return {cells:[...this.index.cells],extent:[...this.index.extent],densityCap:this.index.densityCap,time,fields:{density,temperature},model:'baked-float32-vpa1'};
  }finally{this.#busy=false;}
 }
 clear(){this.#generation++;this.#cache.clear();}dispose(){this.#closed=true;this.clear();}
}
// Limit incoming bytes even when Content-Length is missing or misleading.
async function fetchBounded(url,max,signal){
 const response=await fetch(url,{signal});if(!response.ok||!response.body)throw Error(`VPA fetch failed (${response.status})`);
 const length=response.headers.get('content-length');if(length!==null&&Number(length)>max)throw RangeError('VPA response too large');
 const reader=response.body.getReader(),chunks=[];let n=0;
 try{for(;;){const {done,value}=await reader.read();if(done)break;n+=value.byteLength;if(n>max)throw RangeError('VPA response too large');chunks.push(value);}}
 catch(e){await reader.cancel().catch(()=>{});throw e;}finally{reader.releaseLock();}
 const out=new Uint8Array(n);let offset=0;for(const a of chunks){out.set(a,offset);offset+=a.byteLength;}return out;
}
export async function openFieldSequence(indexUrl,{signal}={}){
 const url=new URL(indexUrl,globalThis.location?.href);const idx=await fetchBounded(url,MAX_INDEX,signal);
 return new FieldSequence(idx,(i,n)=>fetchBounded(new URL(frameFilename(i),url),n,signal));
}
/** Explicit baked sequence GPU bridge. Does not own the sequence or GPU device.
 * Call seek at a chosen upload cadence; do not overlap seeks. Keep rendering the
 * prior committed source until seek resolves. No GPU readback or simulation. */
export class GpuSequencePlayer {
 #busy=false;#closed=false;#source=null;#time=null;
 constructor(device,sequence,options={}){this.device=device;this.sequence=sequence;this.options=options;}
 get time(){return this.#time;}get source(){return this.#source;}
 async seek(time){if(this.#busy||this.#closed)throw Error('player disposed or upload pending');this.#busy=true;try{const f=await this.sequence.sample(time);if(this.#closed)throw Error('player disposed');if(this.#source)await this.#source.replace(f);else{const s=await GpuFieldVolume.create(this.device,f,{...this.options,reuseBuffers:true});if(this.#closed){s.dispose();throw Error('player disposed');}this.#source=s;}if(this.#closed)throw Error('player disposed');this.#time=f.time;return this.#source;}finally{this.#busy=false;}}
 dispose(){this.#closed=true;this.#source?.dispose();this.#source=null;}
}
