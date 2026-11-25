/** Standalone, same-device WebGPU volume draw. No atlas packing, mapping, or CPU transfer.
 * One queue submission per draw. Renderer owns only its uniform buffer; never owns the solver/device/view. */
const sub=(a,b)=>a.map((x,i)=>x-b[i]),cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
const vec=(x,name)=>{if(!Array.isArray(x)||x.length!==3||x.some(v=>!Number.isFinite(v)||Math.abs(v)>1e7))throw new RangeError(`invalid ${name}`);return x;};
function unit(v){const l=Math.hypot(...v);if(!Number.isFinite(l)||l<1e-7)throw new RangeError('degenerate camera/light vector');return v.map(x=>x/l);}
const bounded=(v,lo,hi,name)=>{if(!Number.isFinite(v)||v<lo||v>hi)throw new RangeError(`invalid ${name}`);return v;};
const backgrounds={transparent:0,dark:1,sky:2};
export function packVolumeView(source,{eye,target,up=[0,1,0],aspect=1,fov=40,material,light=[-.45,.8,.35],steps=64,shadowSteps=6,background='dark'}={}){
    if(!['mac','detail'].includes(source.layout)||!source.cells.every(x=>Number.isInteger(x)&&x>=4&&x<=(source.layout==='detail'?768:192))||source.cells.length!==3||source.cells.reduce((a,n)=>a*n,1)>2097152||vec(source.extent,'extent').some(x=>x<=0))throw new RangeError('invalid source geometry');
    const origin=vec(source.origin,'origin'),o=sub(vec(eye,'eye'),origin),f=unit(sub(vec(target,'target'),eye)),r=unit(cross(f,vec(up,'up'))),u=unit(cross(r,f)),l=unit(vec(light,'light'));
    bounded(aspect,.05,20,'aspect');bounded(fov,5,140,'fov');if(!Number.isInteger(steps)||steps<8||steps>256||!Number.isInteger(shadowSteps)||shadowSteps<0||shadowSteps>16||!Object.hasOwn(backgrounds,background))throw new RangeError('invalid ray budget/background');
    const m=material;if(!m||vec(m.colour,'colour').some(x=>x<0||x>1))throw new RangeError('invalid material colour');
    for(const [k,min,max] of [['extinction',0,1000],['anisotropy',-.9,.9],['albedo',0,1],['emission',0,10],['thermalFade',0,1],['ambient',0,1]])bounded(m[k],min,max,k);
    const bytes=new ArrayBuffer(160),floats=new Float32Array(bytes),ints=new Uint32Array(bytes);ints.set([...source.cells,source.layout==='detail'?1:0],0);floats.set([...source.extent,0],4);floats.set([...o,0],8);floats.set([...f,Math.tan(fov*Math.PI/360)],12);floats.set([...r,aspect],16);floats.set([...u,0],20);floats.set([...m.colour,m.extinction],24);floats.set([m.anisotropy,m.albedo,m.emission,m.thermalFade],28);floats.set([...l,m.ambient],32);ints.set([steps,shadowSteps,backgrounds[background],0],36);return bytes;
}
export class GpuVolumeRenderer {
    static async create(simulation,{format='bgra8unorm-srgb',enableSceneDepth=false,shaderURL=new URL('./shaders/render/volume.wgsl',import.meta.url)}={}){
        if(typeof simulation?.renderSource!=='function')throw new TypeError('GPU or Hybrid simulation required; CPU/procedural use CPU preview or texture upload');
        if(typeof enableSceneDepth!=='boolean')throw new TypeError('enableSceneDepth must be boolean');
        const source=simulation.renderSource(),device=source.device;
        const response=await fetch(shaderURL);if(!response.ok)throw new Error(`Vapor render shader: HTTP ${response.status}`);
        const shader=device.createShaderModule({label:'vapor-direct-volume',code:await response.text()});
        const info=await shader.getCompilationInfo(),errors=info.messages.filter(m=>m.type==='error');if(errors.length)throw new Error(errors.map(e=>`${e.lineNum}:${e.linePos} ${e.message}`).join('\n'));
        const layout=device.createBindGroupLayout({entries:[{binding:0,visibility:GPUShaderStage.FRAGMENT,buffer:{type:'uniform',minBindingSize:160}},{binding:1,visibility:GPUShaderStage.FRAGMENT,buffer:{type:'read-only-storage'}}]});
        // Target must use a linear or sRGB renderable format selected by the host.
        const pipeline=await device.createRenderPipelineAsync({label:'vapor-direct-volume',layout:device.createPipelineLayout({bindGroupLayouts:[layout]}),vertex:{module:shader,entryPoint:'vertex_main'},fragment:{module:shader,entryPoint:'fragment_main',targets:[{format,blend:{color:{srcFactor:'one',dstFactor:'one-minus-src-alpha'},alpha:{srcFactor:'one',dstFactor:'one-minus-src-alpha'}}}]},primitive:{topology:'triangle-list'}});
        let depthLayout=null,depthPipeline=null;
        if(enableSceneDepth){
            depthLayout=device.createBindGroupLayout({entries:[{binding:0,visibility:GPUShaderStage.FRAGMENT,buffer:{type:'uniform',minBindingSize:160}},{binding:1,visibility:GPUShaderStage.FRAGMENT,buffer:{type:'read-only-storage'}},{binding:2,visibility:GPUShaderStage.FRAGMENT,texture:{sampleType:'unfilterable-float',viewDimension:'2d',multisampled:false}}]});
            depthPipeline=await device.createRenderPipelineAsync({label:'vapor-scene-depth-volume',layout:device.createPipelineLayout({bindGroupLayouts:[depthLayout]}),vertex:{module:shader,entryPoint:'vertex_main'},fragment:{module:shader,entryPoint:'fragment_scene_depth',targets:[{format,blend:{color:{srcFactor:'one',dstFactor:'one-minus-src-alpha'},alpha:{srcFactor:'one',dstFactor:'one-minus-src-alpha'}}}]},primitive:{topology:'triangle-list'}});
        }
        if(simulation.renderSource().device!==device)throw new Error('simulation device changed');
        return new GpuVolumeRenderer(simulation,device,layout,pipeline,format,depthLayout,depthPipeline);
    }
    constructor(simulation,device,layout,pipeline,format,depthLayout,depthPipeline){this.simulation=simulation;this.device=device;this.layout=layout;this.pipeline=pipeline;this.format=format;this.depthLayout=depthLayout;this.depthPipeline=depthPipeline;this.uniform=device.createBuffer({label:'vapor-volume-view',size:160,usage:GPUBufferUsage.UNIFORM|GPUBufferUsage.COPY_DST});this.groups=new Map();this.closed=false;this.draws=0;}
    /** Submit immediately; never retain a borrowed source across step/reset/dispose. */
    render(view,options={}){
        if(this.closed)throw new Error('renderer disposed');if(!view)throw new TypeError('render texture view required');const source=this.simulation.renderSource();if(source.device!==this.device)throw new Error('simulation device changed');
        const {load=false,sceneDepth,width,height,...camera}=options;if(typeof load!=='boolean')throw new TypeError('load must be boolean');
        let depthView=null;
        if(sceneDepth!==undefined){
            if(!this.depthPipeline)throw new Error('renderer was not created with enableSceneDepth');
            if(load!==true||(camera.background!==undefined&&camera.background!=='transparent'))throw new RangeError('scene depth requires load:true and transparent background');
            if(!Number.isInteger(width)||!Number.isInteger(height)||width<1||height<1||width>this.device.limits.maxTextureDimension2D||height>this.device.limits.maxTextureDimension2D)throw new RangeError('invalid scene target dimensions');
            if(!sceneDepth||sceneDepth.format!=='r32float'||sceneDepth.dimension!=='2d'||sceneDepth.sampleCount!==1||sceneDepth.depthOrArrayLayers!==1||sceneDepth.width!==width||sceneDepth.height!==height||!(sceneDepth.usage&GPUTextureUsage.TEXTURE_BINDING)||typeof sceneDepth.createView!=='function')throw new RangeError('scene depth requires matching sampleable single-layer r32float texture');
            if(camera.aspect!==undefined&&Math.abs(camera.aspect-width/height)>1e-6)throw new RangeError('scene depth camera aspect mismatch');
            camera.aspect=width/height;camera.background='transparent';
            depthView=sceneDepth.createView({dimension:'2d',baseMipLevel:0,mipLevelCount:1,baseArrayLayer:0,arrayLayerCount:1});
        }
        const packet=packVolumeView(source,camera);
        const entries=[{binding:0,resource:{buffer:this.uniform}},{binding:1,resource:{buffer:source.buffer}}];
        let group;
        if(depthView){group=this.device.createBindGroup({layout:this.depthLayout,entries:[...entries,{binding:2,resource:depthView}]});}
        else{group=this.groups.get(source.buffer);if(!group){group=this.device.createBindGroup({layout:this.layout,entries});this.groups.set(source.buffer,group);}}
        const encoder=this.device.createCommandEncoder({label:'vapor-direct-volume'});const pass=encoder.beginRenderPass({colorAttachments:[{view,loadOp:load?'load':'clear',storeOp:'store',clearValue:{r:0,g:0,b:0,a:0}}]});pass.setPipeline(depthView?this.depthPipeline:this.pipeline);pass.setBindGroup(0,group);pass.draw(3);pass.end();
        // Submit uniform update and draw in queue order, safe even with multiple successive calls.
        this.device.queue.writeBuffer(this.uniform,0,packet);this.device.queue.submit([encoder.finish()]);this.draws++;
    }
    dispose(){if(this.closed)return;this.closed=true;this.groups.clear();this.uniform.destroy();}
}
