#!/usr/bin/env python3
"""Actual browser GPU/Hybrid rendering + canvas captures. No mock device, no CPU substitution.
Hybrid requires a current Rust CPU WASM receipt. Software adapters require explicit opt-in.
"""
from __future__ import annotations
import argparse, functools, http.server, json, threading, traceback
from pathlib import Path
from runtime_common import ROOT, require_receipt, sha256, clear_previous_outputs

INIT = '''async ({mode,key,allowSoftware})=>{
 const {createEffect}=await import('/bindings/web/effects.mjs');
 const {GpuVolumeRenderer}=await import('/bindings/web/gpu-render.mjs');
 const e=await createEffect(key,{quality:'low',execution:{backend:mode,detailScale:mode==='hybrid'?2:1,allowSoftwareGpu:allowSoftware}});
 if(e.backend!==mode||e.simulation.backendInfo.initFallback)throw new Error('unexpected backend');
 const canvas=document.querySelector('#canvas'),ctx=canvas.getContext('webgpu'),device=e.simulation.renderSource().device;
 if(!ctx)throw new Error('WebGPU canvas unavailable');
 const base=navigator.gpu.getPreferredCanvasFormat(),format=base+'-srgb';ctx.configure({device,format:base,viewFormats:[format],alphaMode:'opaque'});
 const r=await GpuVolumeRenderer.create(e.simulation,{format});
 const c=e.extent.map((v,i)=>v/2+e.config.origin[i]),span=Math.max(...e.extent),options={eye:[c[0]+span*.5,c[1]+span*.15,c[2]-span*1.65],target:c,material:e.definition.material,aspect:canvas.width/canvas.height,steps:80,shadowSteps:6};
 async function draw(){r.render(ctx.getCurrentTexture().createView({format}),options);await device.queue.onSubmittedWorkDone();await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));}
 window.__vaporValidation={e,r,ctx,draw,device};await draw();return {backend:e.backend,adapter:e.simulation.backendInfo,readback:e.simulation.readbackStats};
}'''
ADVANCE = '''async (frames)=>{const {e,r,draw,device}=window.__vaporValidation;e.play();let submissions=0;
 for(let i=0;i<frames;i++){e.advance(e.config.fixedDt);if(i%8===7||i===frames-1){await draw();submissions++;}}
 await device.queue.onSubmittedWorkDone();const stats=e.simulation.readbackStats;
 if(stats.allocations!==0||stats.completed!==0||stats.bytesCopied!==0)throw new Error('render unexpectedly used readback');
 if(r.draws!==submissions+1)throw new Error('render submission mismatch');return {time:e.time,draws:r.draws,renderReadback:stats};}'''
DIAGNOSTICS = '''async ()=>{const {e,r,ctx}=window.__vaporValidation;try{const metrics=await e.simulation.metrics(),atlas=await e.atlasRGBA8();let max=0;for(let i=0;i<atlas.length;i+=4)max=Math.max(max,atlas[i]);if(metrics.nonFinite!==0||!(metrics.densityIntegral>0)||max===0)throw new Error('empty or nonfinite field');return {metrics,maxDensityByte:max,atlasBytes:atlas.length,explicitReadback:e.simulation.readbackStats};}finally{r.dispose();ctx.unconfigure();e.dispose();delete window.__vaporValidation;}}'''

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--modes',nargs='+',choices=['gpu','hybrid'],default=['gpu','hybrid']);p.add_argument('--presets',nargs='+',choices=['cigarette_smoke','exhaled_aerosol','steam','smoke','flame'],default=['cigarette_smoke','exhaled_aerosol']);p.add_argument('--frames',type=int,default=72);p.add_argument('--allow-software',action='store_true');p.add_argument('--headless',action='store_true');p.add_argument('--channel',choices=['chrome','msedge']);p.add_argument('--browser');p.add_argument('--timeout',type=int,default=180000);a=p.parse_args()
    if not 24<=a.frames<=240:p.error('frames must be 24..240')
    if a.channel and a.browser:p.error('choose channel or browser, not both')
    modes=list(dict.fromkeys(a.modes));keys=list(dict.fromkeys(a.presets));out=ROOT/'reports/local/webgpu-direct';out.mkdir(parents=True,exist_ok=True)
    names=[f'{mode}-{key}-{phase}.png' for mode in modes for key in keys for phase in ('blank','active')];clear_previous_outputs(out,['validation.json',*names]);report={'status':'BLOCKED','evidence':'Actual WebGPU compute and same-device direct renderer; explicit diagnostics after rendering; NOT native engine capture','modes':modes,'presets':keys,'allow_software':a.allow_software,'checks':[]};code=2
    try:
        if 'hybrid' in modes:report['wasm_receipt']=require_receipt(ROOT/'bindings/web/vapor.wasm')
        from playwright.sync_api import sync_playwright
        from PIL import Image,ImageChops
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
                        for key in keys:
                            row={'mode':mode,'preset':key,'status':'FAIL'};page=browser.new_page(viewport={'width':1280,'height':900},device_scale_factor=1);page.set_default_timeout(a.timeout);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                            try:
                                page.goto(f'http://127.0.0.1:{server.server_port}/examples/webgpu-volume/',timeout=a.timeout)
                                row['initial']=page.evaluate(INIT,{'mode':mode,'key':key,'allowSoftware':a.allow_software});blank=out/f'{mode}-{key}-blank.png';active=out/f'{mode}-{key}-active.png';page.locator('#canvas').screenshot(path=str(blank));row['render']=page.evaluate(ADVANCE,a.frames);page.locator('#canvas').screenshot(path=str(active));row['diagnostics']=page.evaluate(DIAGNOSTICS)
                                with Image.open(blank) as b,Image.open(active) as c:
                                    if b.size!=c.size:raise RuntimeError('canvas size changed')
                                    diff=ImageChops.difference(b.convert('RGB'),c.convert('RGB'));changed=sum(max(pixel)>2 for pixel in diff.getdata());pixels=b.width*b.height
                                if changed<max(8,pixels*.0001):raise RuntimeError('active frame is visually indistinguishable from blank')
                                if errors:raise RuntimeError(str(errors))
                                row.update(status='PASS',changed_pixels=changed,total_pixels=pixels,images=[{'file':f.name,'sha256':sha256(f)} for f in [blank,active]])
                            except Exception as e:
                                row.update(error=str(e),traceback=traceback.format_exc());row['status']='BLOCKED' if 'ERR_BLOCKED_BY_ADMINISTRATOR' in str(e) or 'WebGPU is unavailable' in str(e) or 'No WebGPU compute adapter' in str(e) else 'FAIL'
                            finally:page.close();report['checks'].append(row);print(row['status'],mode,key,flush=True)
                finally:browser.close()
        finally:server.shutdown();server.server_close();thread.join(5)
        report['status']='PASS' if all(r['status']=='PASS' for r in report['checks']) else 'BLOCKED' if all(r['status']=='BLOCKED' for r in report['checks']) else 'FAIL';code={'PASS':0,'FAIL':1,'BLOCKED':2}[report['status']]
    except Exception as e:
        report['error']=str(e);report['status']='BLOCKED' if isinstance(e,(ImportError,FileNotFoundError,OSError)) or 'Executable doesn\'t exist' in str(e) else 'FAIL';code=2 if report['status']=='BLOCKED' else 1
    (out/'validation.json').write_text(json.dumps(report,indent=2)+'\n');print(report['status'],out/'validation.json');return code
if __name__=='__main__':raise SystemExit(main())
