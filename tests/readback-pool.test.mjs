// Resource lifecycle/transfer control tests with a stateful device double.
// No WGSL execution, fluid numerics, GPU timing, or hardware performance claims.
import test,{before,after} from 'node:test';
import assert from 'node:assert/strict';
import {ReadbackPool} from '../bindings/web/readback-pool.mjs';
before(()=>{globalThis.GPUBufferUsage={MAP_READ:1,COPY_DST:2};globalThis.GPUMapMode={READ:1};});
after(()=>{delete globalThis.GPUBufferUsage;delete globalThis.GPUMapMode;});
function device({manual=false}={}) {
    const d={buffers:[],submissions:0,limits:{maxBufferSize:4096}};
    d.createBuffer=options=>{
        const b={...options,bytes:new ArrayBuffer(options.size),state:'idle',unmaps:0,destroyed:false,
            mapAsync(mode,offset=0,size=this.size){
                assert.equal(offset%8,0);assert.equal(size%4,0);assert.equal(this.state,'idle');
                this.state='pending';
                return new Promise((resolve,reject)=>{
                    this.reject=reject;this.complete=()=>{if(this.state!=='pending')return;this.state='mapped';resolve();};
                    if(!manual)queueMicrotask(()=>this.complete());
                });
            },
            getMappedRange(offset=0,size=this.size){assert.equal(this.state,'mapped');return this.bytes.slice(offset,offset+size);},
            unmap(){this.unmaps++;if(this.state==='pending')this.reject(new Error('mapping cancelled'));this.state=this.destroyed?'destroyed':'idle';},
            destroy(){this.destroyed=true;this.unmap();},
        };d.buffers.push(b);return b;
    };
    d.createCommandEncoder=()=>{
        const copies=[];
        return {copyBufferToBuffer(a,ao,b,bo,size){copies.push(()=>{assert.equal(b.state,'idle');new Uint8Array(b.bytes,bo,size).set(new Uint8Array(a.bytes,ao,size));});},finish(){return copies;}};
    };
    d.queue={submit(commands){d.submissions++;for(const command of commands)for(const copy of command)copy();}};
    return d;
}
function source(size=16){return {size,bytes:Uint8Array.from({length:size},(_,i)=>i+1).buffer};}
const code=n=>e=>e.code===n;

test('120 sequential snapshots allocate one staging buffer and return owned copies',async()=>{
    const d=device(),p=new ReadbackPool(d),src=source();let first;
    for(let i=0;i<120;i++){
        new Uint8Array(src.bytes)[0]=i;
        const value=await p.read([[src,16]]);first??=value;
        assert.equal(new Uint8Array(value)[0],i);assert.equal(p.pending,0);
    }
    assert.equal(new Uint8Array(first)[0],0);
    assert.equal(p.stats.allocations,1);assert.equal(p.stats.reuses,119);assert.equal(p.stats.completed,120);
    assert.equal(p.stats.bytesCopied,1920);assert.equal(d.buffers[0].state,'idle');
    p.dispose();assert.ok(d.buffers.every(b=>b.destroyed));assert.equal(p.stats.allocatedBytes,0);
});
test('busy pool rejects before encoding, submission or allocation',async()=>{
    const d=device({manual:true}),p=new ReadbackPool(d),src=source();let packed=0;
    const a=p.read([[src,16]],()=>packed++),b=p.read([[src,16]],()=>packed++);
    await assert.rejects(p.read([[src,16]],()=>packed++),code(-10));
    assert.equal(d.submissions,2);assert.equal(packed,2);assert.equal(p.stats.allocations,2);
    d.buffers.forEach(b=>b.complete());const [x,y]=await Promise.all([a,b]);
    assert.notEqual(x,y);assert.equal(p.stats.peakPending,2);p.dispose();
});
test('larger snapshots replace idle buffers, smaller ones reuse without growth',async()=>{
    const d=device(),p=new ReadbackPool(d),src=source(128);
    await p.read([[src,16]]);const small=d.buffers[0];await p.read([[src,128]]);await p.read([[src,32]]);
    assert.ok(small.destroyed);assert.equal(p.stats.buffers,1);assert.equal(p.stats.allocatedBytes,128);
    assert.equal(p.stats.allocations,2);assert.equal(p.stats.reuses,1);p.dispose();
});
test('multiple regions are copied into one map in declared order',async()=>{
    const d=device(),p=new ReadbackPool(d),a=source(12),b=source(8);new Uint8Array(b.bytes).fill(90);
    const x=new Uint8Array(await p.read([[a,12],[b,8]]));
    assert.deepEqual([...x],[1,2,3,4,5,6,7,8,9,10,11,12,...Array(8).fill(90)]);
    assert.equal(d.submissions,1);assert.equal(p.stats.completed,1);p.dispose();
});
test('timeout cancels map, frees failed slot, and reports fail-stop to owner',async()=>{
    const d=device({manual:true}),errors=[],p=new ReadbackPool(d,{timeoutMs:10,onFailure:e=>errors.push(e)});
    await assert.rejects(p.read([[source(),16]]),code(-8));
    assert.equal(errors.length,1);assert.ok(d.buffers[0].destroyed);assert.equal(p.stats.pending,0);
    assert.equal(p.stats.allocatedBytes,0);assert.equal(p.stats.failures,1);p.dispose();
});
test('dispose cancels pending reads immediately, destroys all slots and is idempotent',async()=>{
    const d=device({manual:true}),errors=[],p=new ReadbackPool(d,{onFailure:e=>errors.push(e)});
    const a=p.read([[source(),16]]),b=p.read([[source(),16]]);p.dispose();p.dispose();
    await Promise.all([assert.rejects(a,code(-2)),assert.rejects(b,code(-2))]);
    assert.equal(errors.length,0);assert.ok(d.buffers.every(b=>b.destroyed));assert.equal(p.stats.pending,0);
    await assert.rejects(p.read([[source(),16]]),code(-2));assert.equal(d.submissions,2);
});
test('mapping rejection removes failed buffer and preserves failure cause',async()=>{
    const d=device({manual:true}),errors=[],p=new ReadbackPool(d,{onFailure:e=>errors.push(e)});
    const read=p.read([[source(),16]]);d.buffers[0].reject(new Error('deliberate device loss'));
    await assert.rejects(read,e=>e.code===-8&&e.message.includes('deliberate device loss'));
    assert.equal(errors.length,1);assert.equal(p.stats.buffers,0);assert.ok(d.buffers[0].destroyed);p.dispose();
});
test('invalid sizes and empty/over-budget batches never allocate or submit',async()=>{
    const d=device(),p=new ReadbackPool(d),src=source();
    for(const size of [0,-4,3,20,NaN,Infinity])await assert.rejects(p.read([[src,size]]));
    await assert.rejects(p.read([]));
    await assert.rejects(p.read([[source(4096),4096],[source(4),4]]),code(-4));
    assert.equal(d.submissions,0);assert.equal(d.buffers.length,0);p.dispose();
});
test('encoding errors clean reserved resources and do not submit',async()=>{
    const d=device(),errors=[],p=new ReadbackPool(d,{onFailure:e=>errors.push(e)});
    await assert.rejects(p.read([[source(),16]],()=>{throw new Error('encoder rejected');}),code(-8));
    assert.equal(d.submissions,0);assert.ok(d.buffers.every(b=>b.destroyed));assert.equal(p.pending,0);assert.equal(errors.length,1);p.dispose();
});
test('invalid capacity and timeout limits fail immediately',()=>{
    for(const capacity of [0,9,1.5,NaN])assert.throws(()=>new ReadbackPool(device(),{capacity}),RangeError);
    for(const timeoutMs of [0,-1,NaN,Infinity])assert.throws(()=>new ReadbackPool(device(),{timeoutMs}),RangeError);
});
