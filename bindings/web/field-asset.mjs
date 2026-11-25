/** VPF1: bounded little-endian, planar Float32 density + temperature. No executable data. */
const HEADER=80, MAX=2097152;
const table=Uint32Array.from({length:256},(_,i)=>{let c=i;for(let j=0;j<8;j++)c=(c>>>1)^((c&1)?0xedb88320:0);return c>>>0;});
export function fieldCRC32(bytes){let c=0xffffffff;for(const b of bytes)c=(c>>>8)^table[(c^b)&255];return (c^0xffffffff)>>>0;}
function grid(cells,extent,cap,time){
 if(!cells||cells.length!==3||!Array.from(cells).every(n=>Number.isInteger(n)&&n>=4&&n<=512))throw new RangeError('invalid VPF cells');
 const count=Array.from(cells).reduce((a,b)=>a*b,1);
 if(count>MAX||!extent||extent.length!==3||!Array.from(extent).every(n=>Number.isFinite(n)&&n>=.0001&&n<=1e7)||!Number.isFinite(cap)||cap<.00001||cap>100||!Number.isFinite(time)||time<0||time>1e7)throw new RangeError('invalid VPF grid/time');
 return count;
}
function values(d,t,n,cap){if(!(d instanceof Float32Array)||!(t instanceof Float32Array)||d.length!==n||t.length!==n)throw new RangeError('invalid VPF fields');for(let i=0;i<n;i++)if(!Number.isFinite(d[i])||d[i]<0||d[i]>cap*(1+1e-6)||!Number.isFinite(t[i])||t[i]<0||t[i]>1e5)throw new RangeError('invalid VPF scalar');}
export function encodeFieldAsset(volume,time=0){
 const {cells,extent,densityCap:cap,fields}=volume,n=grid(cells,extent,cap,time),{density:d,temperature:t}=fields;values(d,t,n,cap);
 const b=new Uint8Array(HEADER+n*8),v=new DataView(b.buffer);b.set([86,80,70,49]);v.setUint32(4,HEADER,true);for(let i=0;i<3;i++){v.setUint32(8+4*i,cells[i],true);v.setFloat64(24+8*i,extent[i],true);}v.setFloat64(48,cap,true);v.setFloat64(56,time,true);v.setUint32(72,n*8,true);
 for(let i=0;i<n;i++){v.setFloat32(HEADER+4*i,d[i],true);v.setFloat32(HEADER+4*(n+i),t[i],true);}v.setUint32(64,fieldCRC32(b.subarray(HEADER)),true);return b;
}
export function decodeFieldAsset(input){
 const b=input instanceof ArrayBuffer?new Uint8Array(input):input;if(!(b instanceof Uint8Array)||b.length<HEADER||b.length>HEADER+MAX*8)throw new RangeError('invalid VPF byte count');
 const v=new DataView(b.buffer,b.byteOffset,b.byteLength);if(b[0]!==86||b[1]!==80||b[2]!==70||b[3]!==49||v.getUint32(4,true)!==HEADER||v.getUint32(20,true)!==0||v.getUint32(68,true)!==0||v.getUint32(76,true)!==0)throw new RangeError('unsupported VPF header');
 const cells=[0,1,2].map(i=>v.getUint32(8+4*i,true)),extent=[0,1,2].map(i=>v.getFloat64(24+8*i,true)),densityCap=v.getFloat64(48,true),time=v.getFloat64(56,true),n=grid(cells,extent,densityCap,time);
 if(b.length!==HEADER+n*8||v.getUint32(72,true)!==n*8||fieldCRC32(b.subarray(HEADER))!==v.getUint32(64,true))throw new RangeError('invalid VPF payload length/CRC');
 const density=new Float32Array(n),temperature=new Float32Array(n);for(let i=0;i<n;i++){density[i]=v.getFloat32(HEADER+4*i,true);temperature[i]=v.getFloat32(HEADER+4*(n+i),true);}values(density,temperature,n,densityCap);
 return {cells,extent,densityCap,time,fields:{density,temperature},model:'baked-float32-vpf1'};
}
