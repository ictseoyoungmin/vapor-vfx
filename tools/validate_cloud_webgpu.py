#!/usr/bin/env python3
"""Representative actual WASM cloud -> Float32 WebGPU field -> fidelity draw + depth + cache timing.
No C fixture, JS density fallback, or software GPU unless explicitly allowed.
"""
from __future__ import annotations
import argparse,base64,functools,http.server,json,math,threading,sys
from pathlib import Path
from runtime_common import ROOT,require_receipt,source_fingerprint,sha256,clear_previous_outputs
from check_sdk import atomic_report
from png_codec import write_rgba
RUN=r'''async ({allowSoftware,frames,budget})=>{
 const {loadVapor}=await import('/bindings/web/vapor.mjs');const {NativeFidelityCPU}=await import('/bindings/web/native-fidelity.mjs');const {GpuFieldVolume}=await import('/bindings/web/gpu-field.mjs');const {GpuFidelityVolumeRenderer}=await import('/bindings/web/gpu-fidelity.mjs');const {prepareFidelityVolume}=await import('/bindings/web/fidelity.mjs');
 if(!navigator.gpu)throw Error('WebGPU unavailable');const adapter=await navigator.gpu.requestAdapter({powerPreference:'high-performance'});if(!adapter)throw Error('No WebGPU adapter');const description=adapter.info?.description??'';const software=!!(adapter.info?.isFallbackAdapter??adapter.isFallbackAdapter??/swiftshader|lavapipe|llvmpipe|software/i.test(description));if(software&&!allowSoftware)throw Error('Software GPU not permitted');
 const device=await adapter.requestDevice();const errors=[];const listener=e=>errors.push(e.error?.message??'GPU error');device.addEventListener('uncapturederror',listener);let source,renderer,target,staging,depth;
 const encode=a=>{let s='';for(let i=0;i<a.length;i+=32768)s+=String.fromCharCode(...a.subarray(i,i+32768));return btoa(s);};
 try{
 const scene=await(await fetch('/contracts/cloud-hero.json')).json();const p=scene.profiles.preview;const sdk=new NativeFidelityCPU(await loadVapor());const start=performance.now();const volume=sdk.generate(scene.preset,{quality:scene.quality,cells:p.cells,extent:scene.extent,settings:scene.settings,time:scene.time});const generationMs=performance.now()-start;
 source=await GpuFieldVolume.create(device,volume);renderer=await GpuFidelityVolumeRenderer.create(source,{format:'rgba8unorm-srgb',enableSceneDepth:true});
 const w=320,h=200,bytesPerRow=Math.ceil(w*4/256)*256;target=device.createTexture({size:[w,h],format:'rgba8unorm-srgb',usage:GPUTextureUsage.RENDER_ATTACHMENT|GPUTextureUsage.COPY_SRC});staging=device.createBuffer({size:bytesPerRow*h,usage:GPUBufferUsage.COPY_DST|GPUBufferUsage.MAP_READ});depth=device.createTexture({size:[w,h],format:'r32float',usage:GPUTextureUsage.TEXTURE_BINDING|GPUTextureUsage.COPY_DST});
 const l=scene.lighting,c=scene.camera,opts={eye:c.eye,target:c.target,aspect:w/h,fov:c.fov,steps:96,material:scene.material,light:l.light.direction,sunRadiance:l.light.radiance,sky:l.sky,ground:l.ground,multiScatter:l.multiScatter,lightScale:.5,lightSteps:24,exposure:c.exposure,background:'sky'};
 async function draw(o){const t=performance.now();const diag=renderer.render(target.createView(),o);await device.queue.onSubmittedWorkDone();return {diag,ms:performance.now()-t};}
 async function read(){const enc=device.createCommandEncoder();enc.copyTextureToBuffer({texture:target},{buffer:staging,bytesPerRow,rowsPerImage:h},[w,h,1]);device.queue.submit([enc.finish()]);await staging.mapAsync(GPUMapMode.READ);const b=new Uint8Array(staging.getMappedRange()),a=new Uint8Array(w*h*4);for(let y=0;y<h;y++)a.set(b.subarray(y*bytesPerRow,y*bytesPerRow+w*4),y*w*4);staging.unmap();return a;}
 const first=await draw(opts),actual=await read();const expected=prepareFidelityVolume({...volume,material:scene.material,...l,shadowSteps:24,lightScale:.5}).render({...c,width:w,height:h,steps:96});
 let ss=0,max=0,visible=0,ssVisible=0;for(let i=0;i<w*h;i++){const vis=expected.alpha[i]>.001;if(vis)visible++;for(let k=0;k<3;k++){const d=Math.abs(actual[i*4+k]-expected.rgba[i*4+k]);ss+=d*d;max=Math.max(max,d);if(vis)ssVisible+=d*d;}}
 const rmse=Math.sqrt(ss/(w*h*3)),visibleRmse=Math.sqrt(ssVisible/Math.max(1,visible*3));if(visible<100||first.diag.cacheReused||rmse>2||visibleRmse>4||max>20)throw Error('Cloud CPU/GPU optics comparison failed: '+JSON.stringify({rmse,visibleRmse,max,visible,cache:first.diag}));
 const times=[];for(let i=0;i<frames;i++){const x=await draw({...opts,eye:[c.eye[0]+Math.sin(i*.1)*10,c.eye[1],c.eye[2]]});if(!x.diag.cacheReused)throw Error('camera change invalidated cache');times.push(x.ms);}
 // Front opaque scene: every cloud ray must be clipped before the field. Compare untouched background byte-for-byte.
 const bg={r:.04,g:.09,b:.16,a:1};function clear(){const enc=device.createCommandEncoder();const p=enc.beginRenderPass({colorAttachments:[{view:target.createView(),loadOp:'clear',storeOp:'store',clearValue:bg}]});p.end();device.queue.submit([enc.finish()]);}
 clear();const blank=await read();const stride=bytesPerRow/4,dep=new Float32Array(stride*h);for(let y=0;y<h;y++)dep.fill(.001,y*stride,y*stride+w);device.queue.writeTexture({texture:depth},dep,{bytesPerRow,rowsPerImage:h},[w,h,1]);const clipped=await draw({...opts,background:'transparent',load:true,sceneDepth:depth,width:w,height:h});const front=await read();if(!clipped.diag.cacheReused||front.some((v,i)=>v!==blank[i]))throw Error('depth occlusion or cache reuse failed');
 // Regenerate at later time, replace data once, then confirm optical cache revision is invalidated.
 const later=sdk.generate(scene.preset,{quality:scene.quality,cells:p.cells,extent:scene.extent,settings:scene.settings,time:4});await source.replace(later);const update=await draw(opts);if(update.diag.cacheReused)throw Error('stale optical cache after field replacement');const moved=await read();if(!moved.some((v,i)=>v!==actual[i]))throw Error('field update produced no image change');await device.queue.onSubmittedWorkDone();if(errors.length)throw Error(errors.join('\n'));
 times.sort((a,b)=>a-b);const percentile=q=>times[Math.ceil(q*times.length)-1];return {width:w,height:h,source:'actual-rust-wasm-float32',adapter:{description,software},generationMs,storageBytes:source.bytes,cacheBytes:update.diag.cacheBytes,cacheBuildMs:first.ms,cameraCompletionMs:{p50:percentile(.5),p95:percentile(.95),p99:percentile(.99),samples:times.length},frameBudgetMs:budget,cloudOnlyBudgetPass:!software&&percentile(.95)<=budget,comparison:{rmse,visibleRmse,max,visiblePixels:visible},cacheReuse:true,depthOcclusion:true,fieldUpdate:true,images:{gpu:encode(actual),cpu_reference_same_rust_field:encode(expected.rgba),updated:encode(moved),occluded:encode(front)}};
 }finally{renderer?.dispose();source?.dispose();target?.destroy();staging?.destroy();depth?.destroy();device.removeEventListener('uncapturederror',listener);device.destroy();}
}'''

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--channel',choices=['msedge','chrome']);p.add_argument('--headless',action='store_true');p.add_argument('--allow-software',action='store_true');p.add_argument('--frames',type=int,default=60);p.add_argument('--budget-ms',type=float,default=16.7);p.add_argument('--output',type=Path,default=ROOT/'reports/local/cloud-webgpu');a=p.parse_args()
    if not 4<=a.frames<=600 or not math.isfinite(a.budget_ms) or a.budget_ms<=0:p.error('invalid frame budget or samples')
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=True);names=['gpu','cpu_reference_same_rust_field','updated','occluded'];clear_previous_outputs(out,['validation.json']+[k+'.png' for k in names]);rp=out/'validation.json';report={'schema':'vapor.cloud-webgpu/1','status':'RUNNING','complete':False,'source_fingerprint':source_fingerprint(),'production_release_ready':False,'timing_scope':'single cloud queue-completion wall time at 320x200, not game frame time'};atomic_report(rp,report)
    try:
        report['wasm_receipt']=require_receipt(ROOT/'bindings/web/vapor.wasm');assert 'wasm' in report['wasm_receipt']['features']
        from playwright.sync_api import sync_playwright
        handler=functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(ROOT));server=http.server.ThreadingHTTPServer(('127.0.0.1',0),handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as pw:
                kwargs={'headless':a.headless};
                if a.channel:kwargs['channel']=a.channel
                browser=pw.chromium.launch(**kwargs)
                try:
                    page=browser.new_page();page.set_default_timeout(180000);page.goto(f'http://127.0.0.1:{server.server_port}/examples/fidelity-cloud/');result=page.evaluate(RUN,dict(allowSoftware=a.allow_software,frames=a.frames,budget=a.budget_ms))
                finally:browser.close()
        finally:server.shutdown();server.server_close();thread.join(5)
        images=result.pop('images');report.update(result);report['captures']={}
        if set(images)!=set(names):raise RuntimeError('missing captures')
        for key,value in images.items():
            path=out/(key+'.png');write_rgba(path,result['width'],result['height'],base64.b64decode(value,validate=True));report['captures'][key]=sha256(path)
        report.update(status='PASS',complete=True);code=0
    except (FileNotFoundError,ImportError) as e:report.update(status='BLOCKED',complete=True,reason=str(e));code=2
    except Exception as e:
        blocked=any(x in str(e) for x in ('ERR_BLOCKED_BY_ADMINISTRATOR','WebGPU unavailable','No WebGPU adapter','Software GPU not permitted',"Executable doesn't exist"));report.update(status='BLOCKED' if blocked else 'FAIL',complete=True,reason=str(e));code=2 if blocked else 1
    atomic_report(rp,report);print(report['status'],rp);return code
if __name__=='__main__':raise SystemExit(main())
