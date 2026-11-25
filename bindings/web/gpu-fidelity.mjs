/** Opt-in direct HDR volume renderer. No CPU field transfer. Optical cache
 * belongs to this renderer and is valid only for an exact field revision.
 * Does not replace the legacy renderer or assert GPU execution certification. */
import {packVolumeView} from './gpu-render.mjs';
const LIGHT_BYTES=64,MAX_CACHE=262144;
const finite=(v,lo,hi,name)=>{if(!Number.isFinite(v)||v<lo||v>hi)throw new RangeError(`invalid ${name}`);return v;};
const integer=(v,lo,hi,name)=>{finite(v,lo,hi,name);if(!Number.isInteger(v))throw new RangeError(`invalid ${name}`);return v;};
const vector=(v,name,hi=50)=>{if(!v||v.length!==3)throw new RangeError(`invalid ${name}`);return Array.from(v,x=>finite(x,0,hi,name));};
export function packFidelityLighting(source,{lightScale=.5,lightSteps=16,sunRadiance=[2.6,2.45,2.2],sky=[.07,.105,.18],ground=[.035,.04,.05],multiScatter=.29,exposure=1}={}){
    finite(lightScale,.125,1,'light scale');integer(lightSteps,4,64,'light steps');finite(multiScatter,0,1,'multiple scatter');finite(exposure,.01,20,'exposure');
    if(!source?.cells||source.cells.length!==3||source.cells.some(x=>!Number.isInteger(x)||x<4||x>768))throw new RangeError('invalid field dimensions');
    const cells=source.cells.map(n=>Math.max(4,Math.ceil(n*lightScale))),count=cells.reduce((a,b)=>a*b,1);
    if(count>MAX_CACHE||count*(lightSteps+1)>8_500_000)throw new RangeError('fidelity light cache work budget exceeded; reduce lightScale or lightSteps');
    const bytes=new ArrayBuffer(LIGHT_BYTES),u=new Uint32Array(bytes),f=new Float32Array(bytes);
    u.set([...cells,lightSteps]);f.set([...vector(sunRadiance,'sun radiance'),multiScatter],4);f.set([...vector(sky,'sky radiance'),exposure],8);f.set([...vector(ground,'ground radiance'),0],12);
    return {bytes,cells,count,cacheBytes:count*16};
}
const layoutEntry=(binding,visibility,type,minBindingSize)=>({binding,visibility,buffer:{type,...(minBindingSize===undefined?{}:{minBindingSize})}});
async function shaderText(url){const r=await fetch(url);if(!r.ok)throw new Error(`Vapor fidelity shader HTTP ${r.status}`);return r.text();}
export class GpuFidelityVolumeRenderer {
    static async create(simulation,{format='bgra8unorm-srgb',enableSceneDepth=false,shaderURL=new URL('./shaders/render/volume.wgsl',import.meta.url),fidelityURL=new URL('./shaders/render/fidelity.wgsl',import.meta.url)}={}){
        if(typeof simulation?.renderSource!=='function'||typeof enableSceneDepth!=='boolean')throw new TypeError('GPU field source and boolean enableSceneDepth required');
        const device=simulation.renderSource().device;if(!device)throw new TypeError('GPU device required');
        const code=(await shaderText(shaderURL))+'\n'+(await shaderText(fidelityURL));const shader=device.createShaderModule({label:'vapor-fidelity',code});const info=await shader.getCompilationInfo();const errors=info.messages.filter(m=>m.type==='error');if(errors.length)throw new Error(errors.map(e=>`${e.lineNum}:${e.linePos} ${e.message}`).join('\n'));
        const C=GPUShaderStage.COMPUTE,F=GPUShaderStage.FRAGMENT;
        const base=stage=>[layoutEntry(0,stage,'uniform',160),layoutEntry(1,stage,'read-only-storage'),layoutEntry(3,stage,'uniform',LIGHT_BYTES)];
        const computeLayout=device.createBindGroupLayout({entries:[...base(C),layoutEntry(4,C,'storage')]});
        const drawEntries=[...base(F),layoutEntry(5,F,'read-only-storage')];const drawLayout=device.createBindGroupLayout({entries:drawEntries});
        const cp=entryPoint=>device.createComputePipelineAsync({label:entryPoint,layout:device.createPipelineLayout({bindGroupLayouts:[computeLayout]}),compute:{module:shader,entryPoint}});
        const rp=(layout,entryPoint)=>device.createRenderPipelineAsync({label:entryPoint,layout:device.createPipelineLayout({bindGroupLayouts:[layout]}),vertex:{module:shader,entryPoint:'vertex_main'},fragment:{module:shader,entryPoint,targets:[{format,blend:{color:{srcFactor:'one',dstFactor:'one-minus-src-alpha'},alpha:{srcFactor:'one',dstFactor:'one-minus-src-alpha'}}}]},primitive:{topology:'triangle-list'}});
        const [sun,vertical,draw]=await Promise.all([cp('fidelity_sun_cache'),cp('fidelity_vertical_cache'),rp(drawLayout,'fidelity_fragment')]);
        let depthLayout=null,depth=null;if(enableSceneDepth){depthLayout=device.createBindGroupLayout({entries:[...drawEntries,{binding:2,visibility:F,texture:{sampleType:'unfilterable-float',viewDimension:'2d',multisampled:false}}]});depth=await rp(depthLayout,'fidelity_fragment_depth');}
        if(simulation.renderSource().device!==device)throw new Error('simulation device changed');
        return new GpuFidelityVolumeRenderer(simulation,device,{computeLayout,drawLayout,depthLayout,sun,vertical,draw,depth,format});
    }
    constructor(simulation,device,pipelines){Object.assign(this,pipelines);this.simulation=simulation;this.device=device;this.closed=false;this.draws=0;this.cacheBuilds=0;this.cache=null;this.cacheBytes=0;this.stamp=null;this.uniform=null;this.lighting=null;try{this.uniform=device.createBuffer({label:'fidelity-view',size:160,usage:GPUBufferUsage.UNIFORM|GPUBufferUsage.COPY_DST});this.lighting=device.createBuffer({label:'fidelity-lighting',size:LIGHT_BYTES,usage:GPUBufferUsage.UNIFORM|GPUBufferUsage.COPY_DST});}catch(e){this.uniform?.destroy();this.lighting?.destroy();throw e;}}
    render(view,options={}){
        if(this.closed||!view)throw new Error('disposed renderer or missing target');const s=this.simulation.renderSource();if(s.device!==this.device)throw new Error('simulation device changed');
        const {load=false,sceneDepth,width,height,lightScale,lightSteps,sunRadiance,sky,ground,multiScatter,exposure,...camera}=options;if(typeof load!=='boolean')throw new TypeError('load must be boolean');
        let depthView=null;if(sceneDepth!==undefined){
            if(!this.depth)throw new Error('renderer was not created with enableSceneDepth');
            if(!load||(camera.background!==undefined&&camera.background!=='transparent'))throw new RangeError('scene depth requires load:true and transparent background');
            const limit=this.device.limits.maxTextureDimension2D;integer(width,1,limit,'scene width');integer(height,1,limit,'scene height');
            if(!sceneDepth||sceneDepth.format!=='r32float'||sceneDepth.dimension!=='2d'||sceneDepth.sampleCount!==1||sceneDepth.depthOrArrayLayers!==1||sceneDepth.width!==width||sceneDepth.height!==height||!(sceneDepth.usage&GPUTextureUsage.TEXTURE_BINDING)||typeof sceneDepth.createView!=='function')throw new RangeError('invalid scene depth texture');
            if(camera.aspect!==undefined&&Math.abs(camera.aspect-width/height)>1e-6)throw new RangeError('scene depth camera aspect mismatch');camera.aspect=width/height;camera.background='transparent';depthView=sceneDepth.createView({dimension:'2d',baseMipLevel:0,mipLevelCount:1,baseArrayLayer:0,arrayLayerCount:1});
        }
        if(load&&camera.background!=='transparent')throw new RangeError('load requires transparent background');
        const packet=packVolumeView(s,camera),light=packFidelityLighting(s,{lightScale,lightSteps,sunRadiance,sky,ground,multiScatter,exposure});
        if(light.cacheBytes>Math.min(this.device.limits.maxBufferSize,this.device.limits.maxStorageBufferBindingSize)||Math.ceil(light.count/64)>this.device.limits.maxComputeWorkgroupsPerDimension)throw new RangeError('device light cache limit exceeded');
        const f=new Float32Array(packet),u=new Uint32Array(light.bytes);
        // Only quantities affecting optical depth belong in this key. Camera,
        // radiance, albedo, phase, exposure and display mode do not.
        const key=JSON.stringify([s.layout,...s.cells,...s.extent,...light.cells,u[3],f[27],f[31],f[32],f[33],f[34]]);
        const tracked=s.epoch!==undefined&&s.epoch!==null&&Number.isSafeInteger(s.tick)&&s.tick>=0;
        const reuse=!!(tracked&&this.cache&&this.stamp&&this.stamp.epoch===s.epoch&&this.stamp.tick===s.tick&&this.stamp.buffer===s.buffer&&this.stamp.key===key);
        let cache=this.cache,fresh=false;if(!cache||this.cacheBytes!==light.cacheBytes){cache=this.device.createBuffer({label:'vapor-optical-depth',size:light.cacheBytes,usage:GPUBufferUsage.STORAGE});fresh=true;}
        const entries=[{binding:0,resource:{buffer:this.uniform}},{binding:1,resource:{buffer:s.buffer}},{binding:3,resource:{buffer:this.lighting}}];
        try{
            const encoder=this.device.createCommandEncoder({label:'vapor-fidelity'});
            if(!reuse){const group=this.device.createBindGroup({layout:this.computeLayout,entries:[...entries,{binding:4,resource:{buffer:cache}}]});for(const [pipeline,count] of [[this.sun,light.count],[this.vertical,light.cells[0]*light.cells[2]]]){const pass=encoder.beginComputePass();pass.setPipeline(pipeline);pass.setBindGroup(0,group);pass.dispatchWorkgroups(Math.ceil(count/64));pass.end();}}
            const group=this.device.createBindGroup({layout:depthView?this.depthLayout:this.drawLayout,entries:[...entries,{binding:5,resource:{buffer:cache}},...(depthView?[{binding:2,resource:depthView}]:[])]});
            const pass=encoder.beginRenderPass({colorAttachments:[{view,loadOp:load?'load':'clear',storeOp:'store',clearValue:{r:0,g:0,b:0,a:0}}]});pass.setPipeline(depthView?this.depth:this.draw);pass.setBindGroup(0,group);pass.draw(3);pass.end();
            this.device.queue.writeBuffer(this.uniform,0,packet);this.device.queue.writeBuffer(this.lighting,0,light.bytes);this.device.queue.submit([encoder.finish()]);
        }catch(e){if(fresh)cache.destroy();this.stamp=null;throw e;}
        if(fresh){this.cache?.destroy();this.cache=cache;this.cacheBytes=light.cacheBytes;}if(!reuse)this.cacheBuilds++;this.stamp=tracked?{epoch:s.epoch,tick:s.tick,buffer:s.buffer,key}:null;this.draws++;
        return Object.freeze({cacheReused:reuse,cacheBuilds:this.cacheBuilds,cacheBytes:this.cacheBytes,lightCells:light.cells.slice(),passes:reuse?1:3});
    }
    dispose(){if(this.closed)return;this.closed=true;this.cache?.destroy();this.uniform.destroy();this.lighting.destroy();this.cache=null;this.cacheBytes=0;this.stamp=null;}
}
