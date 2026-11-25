/** Opt-in temporal volume renderer. Three passes, one queue submission, no readback.
 * Static history is the default; changing fields use only optional conservative history.
 * Owns five rgba16float textures (40 bytes/pixel) and two uniforms, not the solver/device.
 */
import {packVolumeView} from './gpu-render.mjs';
const MiB=1024*1024, uniformBytes=336, pixelBytes=40;
const dot=(a,b)=>a.reduce((s,x,i)=>s+x*b[i],0);
const slice=(a,i,n=3)=>Array.from(a.slice(i,i+n));
const blend={color:{srcFactor:'one',dstFactor:'one-minus-src-alpha'},alpha:{srcFactor:'one',dstFactor:'one-minus-src-alpha'}};
function budget(width,height,limit,device){
    if(!Number.isSafeInteger(width)||!Number.isSafeInteger(height)||width<1||height<1||width>device.limits.maxTextureDimension2D||height>device.limits.maxTextureDimension2D||width*height*pixelBytes>limit)throw new RangeError('temporal texture size/memory budget exceeded');
    return width*height*pixelBytes;
}
/** Pure host policy: never use stale history across reset, geometry, optical or camera cuts.
 * Eligibility is not a pixel acceptance metric; the shader applies additional checks. */
export function temporalPolicy(previous,current){
    const reject=reason=>({eligible:false,weight:0,reason});
    if(current.mode==='off'||current.weight===0)return reject('disabled');
    if(!previous)return reject('first-frame');
    if(!current.epoch||!Number.isSafeInteger(current.tick)||!Number.isSafeInteger(previous.tick)||current.tick<0||previous.tick<0||previous.epoch!==current.epoch||current.tick<previous.tick)return reject('field-reset');
    if(previous.mode!==current.mode||previous.weight!==current.weight||previous.width!==current.width||previous.height!==current.height)return reject('settings-changed');
    const a=new Uint32Array(previous.packet),b=new Uint32Array(current.packet);
    // Geometry, material, light and ray budgets; background is composed independently.
    for(let i=0;i<8;i++)if(a[i]!==b[i])return reject('settings-changed');
    for(let i=24;i<38;i++)if(a[i]!==b[i])return reject('settings-changed');
    const f=new Float32Array(previous.packet),g=new Float32Array(current.packet);
    const extent=slice(g,4),diag=Math.hypot(...extent);
    if(dot(slice(f,12),slice(g,12))<.94||dot(slice(f,20),slice(g,20))<.94||Math.hypot(...slice(f,8).map((x,i)=>x-g[i+8]))>.5*diag||Math.abs(f[15]/g[15]-1)>.1||Math.abs(f[19]/g[19]-1)>.1)return reject('camera-cut');
    const dt=current.tick-previous.tick;
    if(dt>0&&current.mode!=='dynamic')return reject('field-changed');
    if(dt>2)return reject('tick-gap');
    return {eligible:true,weight:dt>0?Math.min(current.weight,.35):current.weight,reason:dt>0?'dynamic':'static'};
}
async function moduleFrom(device,url,label){
    const response=await fetch(url);if(!response.ok)throw new Error(`${label}: HTTP ${response.status}`);
    const module=device.createShaderModule({label,code:await response.text()});
    const errors=(await module.getCompilationInfo()).messages.filter(m=>m.type==='error');
    if(errors.length)throw new Error(`${label}: ${errors.map(e=>`${e.lineNum}:${e.linePos} ${e.message}`).join('\n')}`);
    return module;
}
export class GpuTemporalVolumeRenderer {
    static async create(simulation,{format='bgra8unorm-srgb',maxHistoryBytes=48*MiB,shaderURL=new URL('./shaders/render/volume.wgsl',import.meta.url),temporalShaderURL=new URL('./shaders/render/temporal.wgsl',import.meta.url)}={}){
        if(typeof simulation?.renderSource!=='function')throw new TypeError('GPU or Hybrid simulation required');
        if(!Number.isSafeInteger(maxHistoryBytes)||maxHistoryBytes<40||maxHistoryBytes>128*MiB)throw new RangeError('invalid temporal memory budget');
        const source=simulation.renderSource(),device=source.device,F=GPUShaderStage.FRAGMENT;
        const [march,resolve]=await Promise.all([moduleFrom(device,shaderURL,'vapor-temporal-march'),moduleFrom(device,temporalShaderURL,'vapor-temporal-resolve')]);
        const uniform=(size)=>({binding:0,visibility:F,buffer:{type:'uniform',minBindingSize:size}});
        const texture=binding=>({binding,visibility:F,texture:{sampleType:'unfilterable-float',viewDimension:'2d'}});
        const marchLayout=device.createBindGroupLayout({entries:[uniform(160),{binding:1,visibility:F,buffer:{type:'read-only-storage'}}]});
        const resolveLayout=device.createBindGroupLayout({entries:[uniform(uniformBytes),...[1,2,3,4].map(texture)]});
        const compositeLayout=device.createBindGroupLayout({entries:[uniform(uniformBytes),texture(1)]});
        const pipeline=(label,module,layout,entryPoint,targets)=>device.createRenderPipelineAsync({label,layout:device.createPipelineLayout({bindGroupLayouts:[layout]}),vertex:{module,entryPoint:'vertex_main'},fragment:{module,entryPoint,targets},primitive:{topology:'triangle-list'}});
        const pipelines=await Promise.all([pipeline('vapor-temporal-march',march,marchLayout,'temporal_march',[{format:'rgba16float'},{format:'rgba16float'}]),pipeline('vapor-temporal-resolve',resolve,resolveLayout,'resolve_main',[{format:'rgba16float'}]),pipeline('vapor-temporal-composite',resolve,compositeLayout,'composite_main',[{format,blend}])]);
        if(simulation.renderSource().device!==device)throw new Error('simulation device changed');
        return new GpuTemporalVolumeRenderer(simulation,device,{format,maxHistoryBytes,marchLayout,resolveLayout,compositeLayout,pipelines});
    }
    constructor(simulation,device,config){
        this.simulation=simulation;this.device=device;Object.assign(this,config);this.closed=false;this.draws=0;this._groups=new Map();this._textures=[];this._previous=null;this._slot=0;this._phase=0;this._size=null;this._historyBytes=0;
        const make=(label,size)=>device.createBuffer({label,size,usage:GPUBufferUsage.UNIFORM|GPUBufferUsage.COPY_DST});
        this._viewUniform=make('vapor-temporal-view',160);
        try{this._temporalUniform=make('vapor-temporal-history',uniformBytes);}catch(e){this._viewUniform.destroy();throw e;}
    }
    get historyBytes(){return this._historyBytes;}
    resetHistory(){this._previous=null;this._phase=0;}
    _dropTextures(){for(const t of this._textures)t.destroy();this._textures=[];this._size=null;this._historyBytes=0;this._resolveGroups=null;this._compositeGroups=null;this._raw=null;this._resolved=null;this._geometry=null;this.resetHistory();this._slot=0;}
    _resize(width,height){
        const bytes=budget(width,height,this.maxHistoryBytes,this.device);
        if(this._size?.[0]===width&&this._size[1]===height)return;
        // Destroy old history first to keep the renderer's logical allocation bounded.
        this._dropTextures();const d=this.device;
        const make=label=>{const t=d.createTexture({label,size:[width,height,1],format:'rgba16float',usage:GPUTextureUsage.RENDER_ATTACHMENT|GPUTextureUsage.TEXTURE_BINDING});this._textures.push(t);return t.createView();};
        const bind=(layout,views)=>d.createBindGroup({layout,entries:[{binding:0,resource:{buffer:this._temporalUniform}},...views.map((resource,i)=>({binding:i+1,resource}))]});
        try{
            this._raw=make('vapor-temporal-raw');this._geometry=[make('vapor-temporal-anchor-a'),make('vapor-temporal-anchor-b')];this._resolved=[make('vapor-temporal-resolved-a'),make('vapor-temporal-resolved-b')];
            this._resolveGroups=[0,1].map(i=>bind(this.resolveLayout,[this._raw,this._geometry[i],this._resolved[1-i],this._geometry[1-i]]));
            this._compositeGroups=this._resolved.map(v=>bind(this.compositeLayout,[v]));
            this._size=[width,height];this._historyBytes=bytes;
        }catch(e){this._dropTextures();throw e;}
    }
    render(view,{width,height,historyMode='static',historyWeight=.8,load=false,...camera}={}){
        if(this.closed)throw new Error('renderer disposed');if(!view)throw new TypeError('render texture view required');if(camera.sceneDepth!==undefined)throw new RangeError('scene depth is direct-renderer only; temporal scene rejection not implemented');
        if(!['off','static','dynamic'].includes(historyMode)||!Number.isFinite(historyWeight)||historyWeight<0||historyWeight>.9||typeof load!=='boolean')throw new RangeError('invalid temporal controls');
        const source=this.simulation.renderSource();if(source.device!==this.device)throw new Error('simulation device changed');
        budget(width,height,this.maxHistoryBytes,this.device);
        const packet=packVolumeView(source,{aspect:width/height,...camera});this._resize(width,height);
        const current={epoch:source.epoch,tick:source.tick,packet,width,height,mode:historyMode,weight:historyWeight};
        const decision=temporalPolicy(this._previous,current);
        const phase=decision.eligible?this._phase%8+1:0;
        new Uint32Array(packet)[39]=phase;
        const history=new ArrayBuffer(uniformBytes),data=new Uint8Array(history);data.set(new Uint8Array(packet));data.set(new Uint8Array(this._previous?.packet??packet),160);
        const grid=source.extent.map((x,i)=>x/source.cells[i]);
        // Representative-point tolerance: two cells, capped at 12% of the domain diagonal.
        const tolerance=Math.min(2*Math.hypot(...grid),.12*Math.hypot(...source.extent));
        new Float32Array(history,320,4).set([decision.eligible?1:0,decision.weight,tolerance,decision.reason==='dynamic'?.12:.18]);
        let marchGroup=this._groups.get(source.buffer);if(!marchGroup){marchGroup=this.device.createBindGroup({layout:this.marchLayout,entries:[{binding:0,resource:{buffer:this._viewUniform}},{binding:1,resource:{buffer:source.buffer}}]});this._groups.set(source.buffer,marchGroup);}
        const slot=this._slot,encoder=this.device.createCommandEncoder({label:'vapor-temporal-volume'});
        const attachment=(v,keep=false)=>({view:v,loadOp:keep?'load':'clear',storeOp:'store',clearValue:{r:0,g:0,b:0,a:0}});
        const draw=(index,label,group,attachments)=>{const pass=encoder.beginRenderPass({label,colorAttachments:attachments});pass.setPipeline(this.pipelines[index]);pass.setBindGroup(0,group);pass.draw(3);pass.end();};
        draw(0,'vapor-temporal-march',marchGroup,[attachment(this._raw),attachment(this._geometry[slot])]);
        draw(1,'vapor-temporal-resolve',this._resolveGroups[slot],[attachment(this._resolved[slot])]);
        draw(2,'vapor-temporal-composite',this._compositeGroups[slot],[attachment(view,load)]);
        this.device.queue.writeBuffer(this._viewUniform,0,packet);this.device.queue.writeBuffer(this._temporalUniform,0,history);this.device.queue.submit([encoder.finish()]);
        this._previous=current;this._slot=1-slot;this._phase=phase;this.draws++;
        return Object.freeze({historyEligible:decision.eligible,historyWeight:decision.weight,reason:decision.reason,historyBytes:this.historyBytes,passes:3});
    }
    dispose(){if(this.closed)return;this.closed=true;this._groups.clear();this._dropTextures();this._viewUniform.destroy();this._temporalUniform.destroy();}
}
