import {ReadbackPool} from './readback-pool.mjs';
import {normalizeConfig,normalizeExecution,packParameters,Scene,planClock,BackendError} from './gpu-protocol.mjs';
import {loadVapor} from './vapor.mjs';
const fields={density:0,temperature:1,pressure:2,solid:3,velocity:4};
const B=()=>globalThis.GPUBufferUsage;
async function files(base){
    const names=['manifest.json','mac.wgsl','detail.wgsl','export.wgsl'];
    const data=await Promise.all(names.map(async n=>{const r=await fetch(new URL(n,base));if(!r.ok)throw new Error(`Vapor shader ${n}: HTTP ${r.status}`);return r.text();}));
    const manifest=JSON.parse(data[0]);if(manifest.version!==2||manifest.detailPhasePeriodSeconds!==16||manifest.workgroup!==64||manifest.paramsBytes!==128||manifest.controlBytes!==3072)throw new BackendError(-1,'GPU shader/host protocol mismatch');
    return {manifest,mac:data[1],detail:data[2],export:data[3]};
}
async function createDevice(options){
    if(options.device)return {device:options.device,owned:false,software:null,description:'host-owned WebGPU device'};
    if(!globalThis.navigator?.gpu)throw new BackendError(-7,'WebGPU is unavailable in this context');
    const adapter=await navigator.gpu.requestAdapter({powerPreference:'high-performance'});
    if(!adapter)throw new BackendError(-7,'No WebGPU compute adapter');
    const description=adapter.info?.description??'';
    const software=!!(adapter.info?.isFallbackAdapter??adapter.isFallbackAdapter??/swiftshader|lavapipe|llvmpipe|software/i.test(description));
    if(software&&!options.allowSoftwareGpu)throw new BackendError(-7,'Software GPU requires allowSoftwareGpu=true');
    let device;try{device=await adapter.requestDevice();}catch(e){throw new BackendError(-7,`WebGPU device unavailable: ${e.message}`);}
    return {device,owned:true,software,description};
}
function configForWasm(c){const {paddedCount,voxelCount,...options}=c;return options;}
function cpuInfo(sim,requested,fallback=false){
    const renderCells=Object.freeze([...sim.config.cells]);
    Object.defineProperty(sim,'backendInfo',{value:Object.freeze({requested,active:'cpu',detailScale:1,flags:1|(fallback?8:0),renderCells,initFallback:fallback,softwareGpu:false})});
    return sim;
}
/** A single async factory. GPU mode does not download/instantiate a CPU WASM solver. */
export async function createVaporSimulation(config={},execution={}){
    const c=normalizeConfig(config),o=normalizeExecution(c,execution);
    const cpu=async()=>{const m=o.module??await loadVapor(o.wasmURL??new URL('./vapor.wasm',import.meta.url));return m.createSimulation(configForWasm(c));};
    if(o.backend==='cpu')return cpuInfo(await cpu(),'cpu');
    let helper=null;
    try{
        if(o.backend==='hybrid')helper=await cpu();
        return await GpuSimulation.create(c,o,helper);
    }catch(e){try{helper?.dispose();}catch{}if(o.backend==='auto'&&o.allowCpuFallback&&e.code===-7)return cpuInfo(await cpu(),'auto',true);throw e;}
}
/** GPU commands are queued, not waited on. Snapshots are asynchronous owned copies. */
export class GpuSimulation {
    static async create(config,options,cpu=null){
        const sim=new GpuSimulation(config,options,cpu);
        try{await sim._init();return sim;}catch(e){try{sim.dispose();}catch{}throw e;}
    }
    constructor(config,options,cpu){
        this.config=config;this.options=options;this.cpu=cpu;this.scene=new Scene(config);
        this._clock={ticks:0,accumulator:0,dropped:0};this._fieldEpoch=Object.freeze({});this._closed=false;this._failure=null;
        this._resources=[];this._reads=null;this._active=0;this._detailActive=0;
    }
    get closed(){return this._closed;}
    get readbackStats(){return this._reads?.stats??null;}
    _check(){if(this._closed)throw new BackendError(-2,'simulation disposed');if(this._failure)throw this._failure;}
    async _init(){
        const ctx=await createDevice(this.options);Object.assign(this,{device:ctx.device,_ownedDevice:ctx.owned});
        this._onError=e=>{if(!this._closed)this._failure=new BackendError(-8,`WebGPU error: ${e.error?.message??'unknown'}`);};
        this.device.addEventListener('uncapturederror',this._onError);
        this._reads=new ReadbackPool(this.device,{timeoutMs:this.options.readbackTimeoutMs,onFailure:error=>{if(!this._closed)this._failure=error;}});
        this.device.lost.then(info=>{if(!this._closed)this._failure=new BackendError(-8,`WebGPU device lost: ${info.message}`);});
        const source=await files(this.options.shaderURL??new URL('./shaders/compute/',import.meta.url));this.manifest=source.manifest;
        const c=this.config,scale=this.options.detailScale,n=c.paddedCount,fine=c.voxelCount*scale**3,limits=this.device.limits;
        for(const size of [n*32,n*16,fine*16,fine*4])if(size>limits.maxBufferSize||size>limits.maxStorageBufferBindingSize)throw new BackendError(-4,'GPU storage buffer limit exceeded');
        if(Math.ceil(Math.max(n,fine)/64)>limits.maxComputeWorkgroupsPerDimension)throw new BackendError(-4,'GPU dispatch limit exceeded');
        const buf=(label,size,usage)=>{const b=this.device.createBuffer({label,size,usage});this._resources.push(b);return b;};
        const usage=B().STORAGE|B().COPY_DST|B().COPY_SRC;
        this.params=buf('vapor-params',128,B().UNIFORM|B().COPY_DST);this.controls=buf('vapor-controls',3072,usage);
        this.state=Array.from({length:3},()=>buf('vapor-MAC',n*32,usage));this.aux=buf('vapor-curl-divergence',n*16,usage);this.counters=buf('vapor-counters',8,usage);
        this.detail=(this.cpu||scale>1)?Array.from({length:3},()=>buf('vapor-detail',fine*16,usage)):null;
        this.dummy=buf('vapor-unused-detail',16,usage);this.atlas=buf('vapor-atlas',fine*4,usage);
        this.device.queue.writeBuffer(this.params,0,packParameters(c,this.options));
        this.device.pushErrorScope('validation');
        try{
            const makeLayout=(kinds)=>this.device.createBindGroupLayout({entries:kinds.map((kind,binding)=>({binding,visibility:GPUShaderStage.COMPUTE,buffer:{type:kind===0?'uniform':kind===1?'read-only-storage':'storage'}}))});
            this.ml=makeLayout([0,1,1,2,1,2,2]);this.dl=makeLayout([0,1,1,1,2,1,2]);this.el=makeLayout([0,1,1,2]);
            const modules={mac:this.device.createShaderModule({label:'vapor-MAC',code:source.mac}),detail:this.device.createShaderModule({label:'vapor-detail',code:source.detail}),export:this.device.createShaderModule({label:'vapor-export',code:source.export})};
            for(const [name,module]of Object.entries(modules)){
                const info=await module.getCompilationInfo();const errors=info.messages.filter(m=>m.type==='error');if(errors.length)throw new BackendError(-8,`${name} WGSL: ${errors.map(e=>`${e.lineNum}:${e.linePos} ${e.message}`).join('\n')}`);
            }
            const make=async(layout,module,entry)=>this.device.createComputePipelineAsync({label:entry,layout:this.device.createPipelineLayout({bindGroupLayouts:[layout]}),compute:{module,entryPoint:entry}});
            this.pipelines=new Map();
            for(const [entry]of [...this.manifest.beforePressure,...this.manifest.pressure,...this.manifest.afterPressure])if(!this.pipelines.has(entry))this.pipelines.set(entry,await make(this.ml,modules.mac,entry));
            for(const [entry]of this.manifest.detail)this.pipelines.set(entry,await make(this.dl,modules.detail,entry));
            this.pipelines.set('pack_main',await make(this.el,modules.export,'pack_main'));this.pipelines.set('pack_detail',await make(this.el,modules.export,'pack_detail'));
            const bind=(layout,buffers)=>this.device.createBindGroup({layout,entries:buffers.map((buffer,binding)=>({binding,resource:{buffer}}))});
            this.mainGroups=[0,1].map(a=>[
                bind(this.ml,[this.params,this.controls,this.state[a],this.state[1-a],this.state[2],this.aux,this.counters]),
                bind(this.ml,[this.params,this.controls,this.state[a],this.state[2],this.state[a],this.aux,this.counters]),
                bind(this.ml,[this.params,this.controls,this.state[1-a],this.state[a],this.state[2],this.aux,this.counters])]);
            this.detailGroups=this.detail?[0,1].map(coarse=>[0,1].map(a=>[
                bind(this.dl,[this.params,this.controls,this.state[coarse],this.detail[a],this.detail[1-a],this.detail[2],this.counters]),
                bind(this.dl,[this.params,this.controls,this.state[coarse],this.detail[a],this.detail[2],this.detail[a],this.counters])])):[];
            this.packGroups=[0,1].map(coarse=>[0,1].map(a=>bind(this.el,[this.params,this.state[coarse],this.detail?.[a]??this.dummy,this.atlas])));
        }finally{const error=await this.device.popErrorScope();if(error)throw new BackendError(-8,`WebGPU pipeline/binding validation: ${error.message}`);}
        this.backendInfo=Object.freeze({requested:this.options.backend,active:this.cpu?'hybrid':'gpu',detailScale:scale,flags:(this.cpu?7:2)|(ctx.software?32:0),renderCells:Object.freeze(c.cells.map(n=>n*scale)),initFallback:false,softwareGpu:ctx.software,adapter:ctx.description,gpuBytes:this._resources.reduce((s,b)=>s+b.size,0),hybridUploadBytes:this.cpu?n*32:0});
        this._check();
    }
    _dispatch(encoder,entry,group,count){const pass=encoder.beginComputePass({label:entry});pass.setPipeline(this.pipelines.get(entry));pass.setBindGroup(0,group);pass.dispatchWorkgroups(Math.ceil(count/64));pass.end();}
    _mainPass(encoder,entry,kind){this._dispatch(encoder,entry,this.mainGroups[this._active][kind==='predict'?1:kind==='inplace'?2:0],this.config.paddedCount);if(kind==='swap')this._active=1-this._active;}
    _tick(){
        this._check();const time=this._clock.ticks*this.config.fixedDt,packet=this.scene.pack(time);
        try{
            if(this.cpu){this.cpu.step(1);const cells=this.cpu.macCells();if(cells.length!==this.config.paddedCount*8)throw new BackendError(-1,'Rust MAC upload layout mismatch');this.device.queue.writeBuffer(this.state[0],0,cells);this._active=0;}
            this.device.queue.writeBuffer(this.params,0,packParameters(this.config,this.options,time));this.device.queue.writeBuffer(this.controls,0,packet);
            const encoder=this.device.createCommandEncoder({label:'vapor-step'});
            if(!this.cpu){
                for(const [entry,kind]of this.manifest.beforePressure)this._mainPass(encoder,entry,kind);
                for(let i=0;i<this.config.pressureIterations;i++)for(const [entry,kind]of this.manifest.pressure)this._mainPass(encoder,entry,kind);
                for(const [entry,kind]of this.manifest.afterPressure)this._mainPass(encoder,entry,kind);
            }
            if(this.detail)for(const [entry,kind]of this.manifest.detail){this._dispatch(encoder,entry,this.detailGroups[this._active][this._detailActive][kind==='predict'?1:0],this.config.voxelCount*this.options.detailScale**3);if(kind==='swap')this._detailActive=1-this._detailActive;}
            this.device.queue.submit([encoder.finish()]);this._clock.ticks++;
        }catch(e){this._failure=e instanceof BackendError?e:new BackendError(-8,String(e.message??e));throw this._failure;}
    }
    step(count=1){this._check();if(!Number.isInteger(count)||count<0||count>600)throw new BackendError(-1,'step count must be 0..600');if(this._clock.ticks+count>Number.MAX_SAFE_INTEGER)throw new BackendError(-4,'tick counter exceeds exact JS integer range');for(let i=0;i<count;i++)this._tick();}
    advance(seconds){this._check();const p=planClock(this._clock,seconds,this.config);this.step(p.steps);this._clock.accumulator=p.residual;this._clock.dropped+=p.dropped;return {steps:p.steps,alpha:p.residual/this.config.fixedDt,droppedSeconds:p.dropped,simulatedSeconds:this._clock.ticks*this.config.fixedDt};}
    _mutate(method,args){this._check();const next=this.scene.clone();next[method](...args);if(this.cpu)this.cpu[method](...args);this.scene=next;}
    setEmitter(...args){this._mutate('setEmitter',args);}removeEmitter(...args){this._mutate('removeEmitter',args);}
    setCapsule(...args){this._mutate('setCapsule',args);}setSphere(...args){this._mutate('setSphere',args);}setBox(...args){this._mutate('setBox',args);}removeObstacle(...args){this._mutate('removeObstacle',args);}
    setProfile(...args){this._mutate('setProfile',args);}
    reset(){
        if(this._closed)throw new BackendError(-2,'simulation disposed');if(this._failure&&this._failure.code!==-5)throw this._failure;if(this._reads?.pending)throw new BackendError(-10,'cannot reset while readbacks are pending');
        this._fieldEpoch=Object.freeze({});
        const e=this.device.createCommandEncoder({label:'vapor-reset'});for(const b of [...this.state,this.aux,this.counters,this.atlas,...(this.detail??[])])e.clearBuffer(b);this.device.queue.submit([e.finish()]);
        this.cpu?.reset();this._clock={ticks:0,accumulator:0,dropped:0};this._active=this._detailActive=0;this._failure=null;
    }
    async _read(regions,encodeBeforeCopy=null){
        this._check();
        const bytes=await this._reads.read(regions,encodeBeforeCopy);
        this._check();
        return bytes;
    }
    _checkCounters(bytes,offset){const v=new DataView(bytes,offset,8);if(v.getUint32(0,true)){this._failure=new BackendError(-5,'non-finite GPU state; reset required');throw this._failure;}return v.getUint32(4,true);}
    /** Borrowed GPU field for a same-device render submission. Consume synchronously
     * before the next step/reset/dispose. Do not map, write or destroy this buffer. */
    renderSource(){
        this._check();
        return Object.freeze({device:this.device,buffer:this.detail?this.detail[this._detailActive]:this.state[this._active],
            layout:this.detail?'detail':'mac',cells:this.backendInfo.renderCells,epoch:this._fieldEpoch,tick:this._clock.ticks,
            extent:Object.freeze(this.config.cells.map(n=>n*this.config.cellSize)),origin:this.config.origin});
    }
    async atlasRGBA8(){
        this._check();
        // Reserving the staging slot precedes both packing and copying. Busy requests do no work.
        const b=await this._read([[this.atlas,this.atlas.size],[this.counters,8]],e=>{
            this._dispatch(e,this.detail?'pack_detail':'pack_main',
                this.packGroups[this._active][this._detailActive],this.atlas.size/4);
        });
        this._checkCounters(b,this.atlas.size);
        return new Uint8Array(b,0,this.atlas.size);
    }
    async _snapshot(){
        const n=this.config.paddedCount,clock={...this._clock};const b=await this._read([[this.state[this._active],n*32],[this.aux,n*16],[this.counters,8]]);
        const clamps=this._checkCounters(b,n*48);return {cells:new Float32Array(b,0,n*8),rhs:new Float32Array(b,n*32,n*4),clamps,clock};
    }
    async macCells(){this._check();if(this.cpu)return this.cpu.macCells();return (await this._snapshot()).cells.slice();}
    async field(name='density'){
        this._check();
        if(!Object.hasOwn(fields,name))throw new BackendError(-1,'unknown field');if(this.cpu)return this.cpu.field(name);
        const {cells:s}=await this._snapshot(),c=this.config,result=new Float32Array(c.voxelCount*(name==='velocity'?3:1));let j=0;
        const idx=(x,y,z)=>8*(x+(c.nx+1)*(y+(c.ny+1)*z));
        for(let z=0;z<c.nz;z++)for(let y=0;y<c.ny;y++)for(let x=0;x<c.nx;x++){const i=idx(x,y,z);if(name==='velocity'){result[j++]=.5*(s[i]+s[idx(x+1,y,z)]);result[j++]=.5*(s[i+1]+s[idx(x,y+1,z)+1]);result[j++]=.5*(s[i+2]+s[idx(x,y,z+1)+2]);}else result[j++]=s[i+4+fields[name]];}return result;
    }
    async metrics(){
        this._check();
        if(this.cpu){const m=this.cpu.metrics();m.droppedSeconds=this._clock.dropped;return m;}
        const {cells:s,rhs,clamps,clock}=await this._snapshot(),c=this.config;
        const m={ticks:clock.ticks,time:clock.ticks*c.fixedDt,densityIntegral:0,maxDensity:0,maxSpeed:0,divergenceRms:0,pressureResidualRms:0,centroid:[0,0,0],nonFinite:0,clampedVelocities:clamps,droppedSeconds:clock.dropped,cpuBytes:0};
        const idx=p=>p[0]+(c.nx+1)*(p[1]+(c.ny+1)*p[2]);let sum=0,div2=0,res2=0,count=0;
        for(let z=0;z<c.nz;z++)for(let y=0;y<c.ny;y++)for(let x=0;x<c.nx;x++){
            const p=[x,y,z],k=idx(p),i=k*8;if(s[i+7]>.5)continue;const rho=s[i+4];sum+=rho;m.maxDensity=Math.max(m.maxDensity,rho);let div=0,speed2=0,pressure=0,denom=0;
            for(let a=0;a<3;a++){m.centroid[a]+=rho*(c.origin[a]+(p[a]+.5)*c.cellSize);const hi=p.slice();hi[a]++;const v=.5*(s[i+a]+s[idx(hi)*8+a]);speed2+=v*v;div+=s[idx(hi)*8+a]-s[i+a];
                for(const sign of [-1,1]){const q=p.slice();q[a]+=sign;if(q[a]>=0&&q[a]<c.cells[a]){const j=idx(q)*8;if(s[j+7]<=.5){pressure+=s[j+6];denom++;}}else if(c.boundary===0)denom++;}}
            m.maxSpeed=Math.max(m.maxSpeed,Math.sqrt(speed2));div2+=(div/c.cellSize)**2;res2+=((pressure-denom*s[i+6])/c.cellSize**2-rhs[k*4+3])**2;count++;
        }
        m.densityIntegral=sum*c.cellSize**3;if(sum>0)m.centroid=m.centroid.map(v=>v/sum);if(count){m.divergenceRms=Math.sqrt(div2/count);m.pressureResidualRms=Math.sqrt(res2/count);}return m;
    }
    dispose(){
        if(this._closed)return;this._closed=true;let error;
        const release=fn=>{try{fn();}catch(e){error??=e;}};
        release(()=>this._reads?.dispose());
        for(const b of this._resources)release(()=>b.destroy());
        this._resources.length=0;
        release(()=>this.cpu?.dispose());
        release(()=>this.device?.removeEventListener('uncapturederror',this._onError));
        if(this._ownedDevice)release(()=>this.device.destroy());
        if(error)throw error;
    }
}
