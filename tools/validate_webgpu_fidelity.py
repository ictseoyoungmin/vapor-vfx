#!/usr/bin/env python3
"""Real WebGPU fidelity-depth shader validation: analytic buffer + actual GPU/Hybrid fluid.
No mock GPU; analytic buffer is explicitly not a fluid simulation. Target readback is
validation only. Requires Playwright and a suitable browser/device, Hybrid needs WASM.
"""
from __future__ import annotations
import argparse,base64,functools,http.server,json,threading,traceback
from runtime_common import ROOT,require_receipt,sha256,clear_previous_outputs
from check_sdk import atomic_report
from png_codec import write_rgba

RUN='''async ({mode,allowSoftware,key})=>{
 const {createEffect}=await import('/bindings/web/effects.mjs');
 const {GpuVolumeRenderer}=await import('/bindings/web/gpu-render.mjs');
 const {GpuFidelityVolumeRenderer}=await import('/bindings/web/gpu-fidelity.mjs');
 const {prepareFidelityVolume,getFidelityPreset}=await import('/bindings/web/fidelity.mjs');
 const e=await createEffect(key,{quality:'low',execution:{backend:mode,detailScale:2,allowSoftwareGpu:allowSoftware}});
 const device=e.simulation.renderSource().device,w=161,h=101,row=Math.ceil(w*4/256)*256,bg=[.1,.2,.3].map(x=>Math.round(x*255)/255);
 let target,depth,staging,analyticBuffer,analytic,direct,fidelity;const errors=[];const onError=x=>errors.push(String(x.error?.message??x.error));device.addEventListener('uncapturederror',onError);
 try{
  if(e.backend!==mode||e.simulation.backendInfo.initFallback)throw Error('unexpected backend');
  target=device.createTexture({size:[w,h,1],format:'rgba8unorm',usage:GPUTextureUsage.RENDER_ATTACHMENT|GPUTextureUsage.COPY_SRC});
  depth=device.createTexture({size:[w,h,1],format:'r32float',usage:GPUTextureUsage.TEXTURE_BINDING|GPUTextureUsage.COPY_DST});
  staging=device.createBuffer({size:row*h,usage:GPUBufferUsage.COPY_DST|GPUBufferUsage.MAP_READ});
  const setDepth=distance=>{const data=new Float32Array(row/4*h);for(let y=0;y<h;y++)data.fill(distance,y*row/4,y*row/4+w);device.queue.writeTexture({texture:depth},data,{bytesPerRow:row,rowsPerImage:h},[w,h,1]);};
  const encode=a=>{let s='';for(let i=0;i<a.length;i+=8192)s+=String.fromCharCode(...a.subarray(i,i+8192));return btoa(s);};
  const draw=async(renderer,options,distance=null)=>{
   const v=target.createView(),encoder=device.createCommandEncoder(),pass=encoder.beginRenderPass({colorAttachments:[{view:v,loadOp:'clear',storeOp:'store',clearValue:{r:bg[0],g:bg[1],b:bg[2],a:1}}]});pass.end();device.queue.submit([encoder.finish()]);
   if(distance!==null)setDepth(distance);const begin=performance.now();
   const diag=renderer.render(v,{...options,aspect:w/h,background:'transparent',load:true,...(distance===null?{}:{sceneDepth:depth,width:w,height:h})});await device.queue.onSubmittedWorkDone();const completionMs=performance.now()-begin;
   const cp=device.createCommandEncoder();cp.copyTextureToBuffer({texture:target},{buffer:staging,bytesPerRow:row,rowsPerImage:h},[w,h,1]);device.queue.submit([cp.finish()]);await staging.mapAsync(GPUMapMode.READ);
   const src=new Uint8Array(staging.getMappedRange()),a=new Uint8Array(w*h*4);for(let y=0;y<h;y++)a.set(src.subarray(y*row,y*row+w*4),y*w*4);staging.unmap();return {a,diag,completionMs};
  };
  const diff=(a,b)=>{let n=0,sum=0,max=0;for(let i=0;i<a.length;i+=4){let pixel=0;for(let c=0;c<3;c++){const d=Math.abs(a[i+c]-b[i+c]);sum+=d*d;max=Math.max(max,d);pixel=Math.max(pixel,d);}if(pixel>1)n++;}return {pixels:n,max,rmse:Math.sqrt(sum/(a.length/4*3))};};
  // Nonuniform analytic input for real GPU-vs-CPU optical comparison. Not a solver result.
  const cells=[8,8,8],extent=[1,1,1],n=512,field=new Float32Array(n*4),density=new Float32Array(n),temperature=new Float32Array(n);
  for(let i=0;i<n;i++){density[i]=.07+.45*((i%8)/7)*((Math.floor(i/8)%8)/7);temperature[i]=.2+(Math.floor(i/64)/7);field[i*4]=density[i];field[i*4+1]=temperature[i];}
  analyticBuffer=device.createBuffer({size:field.byteLength,usage:GPUBufferUsage.STORAGE|GPUBufferUsage.COPY_DST});device.queue.writeBuffer(analyticBuffer,0,field);const epoch={};
  analytic=await GpuFidelityVolumeRenderer.create({renderSource:()=>({device,buffer:analyticBuffer,layout:'detail',cells,extent,origin:[0,0,0],epoch,tick:0})},{format:'rgba8unorm',enableSceneDepth:true});
  const material={colour:[.8,.9,1],extinction:1.3,anisotropy:.3,albedo:.85,ambient:.05,emission:.2,thermalFade:.2},light={direction:[-.5,.7,-.2],radiance:[.9,1,1.1]},sky=[.1,.13,.2],ground=[.03,.025,.02],multiScatter=.25;
  const opts={eye:[.5,.5,-1.4],target:[.5,.5,.5],steps:64,material,light:light.direction,sunRadiance:light.radiance,sky,ground,multiScatter,lightScale:1,lightSteps:24};
  const cpu=prepareFidelityVolume({cells,extent,fields:{density,temperature},densityCap:1,material,light,sky,ground,multiScatter,lightScale:1,shadowSteps:24});const rad=new Float32Array(w*h*3);for(let i=0;i<w*h;i++)rad.set(bg,i*3);const analyticRows=[];
  for(const distance of [0,.5,1.8]){const actual=await draw(analytic,opts,distance);const expected=cpu.render({eye:opts.eye,target:opts.target,width:w,height:h,steps:opts.steps,scene:{depth:new Float32Array(w*h).fill(distance),radiance:rad}});const rgba=new Uint8Array(w*h*4);for(let i=0;i<w*h;i++){for(let c=0;c<3;c++)rgba[i*4+c]=Math.round(255*Math.max(0,Math.min(1,expected.linear[i*3+c])));rgba[i*4+3]=255;}const error=diff(actual.a,rgba);if(error.rmse>1.5||error.max>8||actual.diag.cacheReused!==(distance!==0))throw Error('GPU CPU optical comparison failed '+JSON.stringify({distance,error,diag:actual.diag}));analyticRows.push({distance,error,diag:actual.diag});}
  // Real fluid field: same frozen simulation and material for both direct paths.
  direct=await GpuVolumeRenderer.create(e.simulation,{format:'rgba8unorm'});fidelity=await GpuFidelityVolumeRenderer.create(e.simulation,{format:'rgba8unorm',enableSceneDepth:true});
  const style=getFidelityPreset(key),c=e.extent.map((v,i)=>v/2+e.config.origin[i]),span=Math.max(...e.extent),camera={eye:[c[0]+span*.5,c[1]+span*.15,c[2]-span*1.65],target:c,material:style.material,steps:96,shadowSteps:12,light:style.lighting.light.direction};
  const high={...camera,sunRadiance:style.lighting.light.radiance,sky:style.lighting.sky,ground:style.lighting.ground,multiScatter:style.lighting.multiScatter,lightSteps:24};
  const blank=await draw(fidelity,high,0);e.play();for(let i=0;i<90;i++){e.advance(e.config.fixedDt);if(i%8===7)await device.queue.onSubmittedWorkDone();}
  const classic=await draw(direct,camera),active=await draw(fidelity,high),repeat=await draw(fidelity,high),front=await draw(fidelity,high,.000001);
  const changes={activeVsBlank:diff(active.a,blank.a),repeat:diff(repeat.a,active.a),frontVsBlank:diff(front.a,blank.a),classicVsFidelity:diff(classic.a,active.a)};
  if(changes.activeVsBlank.pixels<8||changes.repeat.pixels||changes.frontVsBlank.pixels||active.diag.cacheReused||!repeat.diag.cacheReused||!front.diag.cacheReused)throw Error('actual fluid/cache comparison failed '+JSON.stringify(changes));
  const readback=e.simulation.readbackStats;if(readback.allocations||readback.completed||readback.bytesCopied)throw Error('renderer unexpectedly read back solver field');await device.queue.onSubmittedWorkDone();if(errors.length)throw Error(errors.join('\\n'));
  return {width:w,height:h,analyticRows,changes,backend:e.backend,adapter:e.simulation.backendInfo,solverReadback:readback,cache:{active:active.diag,repeat:repeat.diag},wallCompletionMs:{classic:classic.completionMs,cacheBuild:active.completionMs,cacheReuse:repeat.completionMs},images:{blank:encode(blank.a),classic:encode(classic.a),active:encode(active.a),front:encode(front.a)}};
 }finally{device.removeEventListener('uncapturederror',onError);analytic?.dispose();direct?.dispose();fidelity?.dispose();analyticBuffer?.destroy();target?.destroy();depth?.destroy();staging?.destroy();e.dispose();}
}'''

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--modes',nargs='+',choices=['gpu','hybrid'],default=['gpu']);p.add_argument('--preset',choices=['cigarette_smoke','exhaled_aerosol','steam','smoke','flame'],default='exhaled_aerosol');p.add_argument('--allow-software',action='store_true');p.add_argument('--headless',action='store_true');p.add_argument('--channel',choices=['chrome','msedge']);p.add_argument('--browser');p.add_argument('--timeout',type=int,default=180000);a=p.parse_args()
    if a.channel and a.browser:p.error('choose channel or browser, not both')
    modes=list(dict.fromkeys(a.modes));out=ROOT/'reports/local/webgpu-fidelity'/a.preset;out.mkdir(parents=True,exist_ok=True);clear_previous_outputs(out,['validation.json',*[f'{m}-{k}.png' for m in ('gpu','hybrid') for k in ('blank','classic','active','front')]])
    report={'schema':'vapor.webgpu-fidelity/1','fidelity_version':'0.16.0','status':'IN_PROGRESS','complete':False,'modes':modes,'preset':a.preset,'allow_software':a.allow_software,'checks':[],'evidence':'Real GPU vs CPU optical comparison on a nonuniform field and actual fluid direct/fidelity renders; explicit render target readback only; completion wall time is not game FPS'};rp=out/'validation.json';atomic_report(rp,report)
    try:
        if 'hybrid' in modes:report['wasm_receipt']=require_receipt(ROOT/'bindings/web/vapor.wasm')
        from playwright.sync_api import sync_playwright
        class Handler(http.server.SimpleHTTPRequestHandler):
            def log_message(self,*args):pass
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(ROOT)));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as pw:
                options={'headless':a.headless}
                if a.channel:options['channel']=a.channel
                if a.browser:options['executable_path']=a.browser
                browser=pw.chromium.launch(**options)
                try:
                    for mode in modes:
                        row={'mode':mode,'status':'FAIL'};page=browser.new_page();page.set_default_timeout(a.timeout)
                        try:
                            page.goto(f'http://127.0.0.1:{server.server_port}/examples/webgpu-volume/',timeout=a.timeout)
                            result=page.evaluate(RUN,{'mode':mode,'allowSoftware':a.allow_software,'key':a.preset});images=result.pop('images');row.update(result);row['images']=[]
                            for key,encoded in images.items():
                                # Shader target is linear UNORM, convert to sRGB for display.
                                raw=bytearray(base64.b64decode(encoded))
                                for i,v in enumerate(raw):
                                    if i%4!=3:
                                        x=v/255;raw[i]=round(255*(12.92*x if x<=.0031308 else 1.055*x**(1/2.4)-.055))
                                path=out/f'{mode}-{key}.png';write_rgba(path,result['width'],result['height'],raw);row['images'].append({'file':path.name,'sha256':sha256(path)})
                            row['status']='PASS'
                        except Exception as e:
                            row.update(error=str(e),traceback=traceback.format_exc());row['status']='BLOCKED' if any(x in str(e) for x in ('ERR_BLOCKED_BY_ADMINISTRATOR','WebGPU is unavailable','No WebGPU compute adapter')) else 'FAIL'
                        finally:page.close();report['checks'].append(row);atomic_report(rp,report);print(row['status'],mode,flush=True)
                finally:browser.close()
        finally:server.shutdown();server.server_close();thread.join(5)
        statuses=[r['status'] for r in report['checks']];report['status']='PASS' if statuses and all(s=='PASS' for s in statuses) else 'BLOCKED' if statuses and all(s=='BLOCKED' for s in statuses) else 'FAIL'
    except Exception as e:
        report['error']=str(e);report['status']='BLOCKED' if isinstance(e,(ImportError,FileNotFoundError,OSError)) or "Executable doesn't exist" in str(e) else 'FAIL'
    report['complete']=True;atomic_report(rp,report);print(report['status'],rp);return {'PASS':0,'FAIL':1,'BLOCKED':2}[report['status']]
if __name__=='__main__':raise SystemExit(main())
