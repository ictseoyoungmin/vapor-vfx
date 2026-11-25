#!/usr/bin/env python3
"""Actual WebGPU temporal renderer checks and PNGs. No mock device or silent CPU fallback.
GPU-only needs no Rust WASM. Hybrid requires a current receipt. MSE is descriptive,
not a universal quality gate; no game FPS or shader pixel-acceptance claim.
"""
from __future__ import annotations
import argparse, functools, http.server, json, threading, traceback
from runtime_common import ROOT, require_receipt, sha256, clear_previous_outputs
from check_sdk import atomic_report

PHASES=('blank','active','direct-low','temporal-static','reference-high','reset')
INIT='''async ({mode,key,allowSoftware,width,height})=>{
 const {createEffect}=await import('/bindings/web/effects.mjs');
 const {GpuVolumeRenderer}=await import('/bindings/web/gpu-render.mjs');
 const {GpuTemporalVolumeRenderer}=await import('/bindings/web/gpu-temporal.mjs');
 const e=await createEffect(key,{quality:'low',execution:{backend:mode,detailScale:mode==='hybrid'?2:1,allowSoftwareGpu:allowSoftware}});
 if(e.backend!==mode||e.simulation.backendInfo.initFallback)throw Error('unexpected backend');
 const canvas=document.querySelector('#canvas');canvas.width=width;canvas.height=height;canvas.style.width=width+'px';canvas.style.height=height+'px';
 const ctx=canvas.getContext('webgpu'),device=e.simulation.renderSource().device;
 if(!ctx)throw Error('WebGPU canvas unavailable');const base=navigator.gpu.getPreferredCanvasFormat(),format=base+'-srgb';ctx.configure({device,format:base,viewFormats:[format],alphaMode:'opaque'});
 const direct=await GpuVolumeRenderer.create(e.simulation,{format}),temporal=await GpuTemporalVolumeRenderer.create(e.simulation,{format});
 const c=e.extent.map((v,i)=>v/2+e.config.origin[i]),span=Math.max(...e.extent),options={eye:[c[0]+span*.5,c[1]+span*.15,c[2]-span*1.65],target:c,material:e.definition.material,aspect:width/height,steps:12,shadowSteps:4};
 const submitted=async()=>{await device.queue.onSubmittedWorkDone();await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));};
 const draw=async({kind='temporal',historyMode='static',...opts}={})=>{const view=ctx.getCurrentTexture().createView({format});let result=null;if(kind==='direct')direct.render(view,{...options,...opts});else result=temporal.render(view,{...options,...opts,width,height,historyMode});await submitted();return result;};
 window.__vaporTemporal={e,device,ctx,direct,temporal,draw,options,span};
 const first=await draw();if(first.historyEligible||first.historyBytes!==width*height*40)throw Error('initial history contract');return {backend:e.backend,adapter:e.simulation.backendInfo,first};
}'''
ACTIVE='''async frames=>{const {e,draw}=window.__vaporTemporal;e.play();for(let i=0;i<frames;i++){e.advance(e.config.fixedDt);if(i%8===7||i===frames-1)await draw({historyMode:'dynamic'});}
 const before=e.simulation.renderSource().tick;e.advance(e.config.fixedDt);const after=e.simulation.renderSource().tick;const dynamic=await draw({historyMode:'dynamic'});
 if(after-before!==1||dynamic.reason!=='dynamic'||dynamic.historyWeight>.35)throw Error('dynamic policy contract');
 const stats=e.simulation.readbackStats;if(stats.allocations||stats.completed||stats.bytesCopied)throw Error('unexpected render readback');return {dynamic,time:e.time,renderReadback:stats};}'''
STATIC='''async ()=>{const {draw,temporal}=window.__vaporTemporal;temporal.resetHistory();let results=[];for(let i=0;i<9;i++)results.push(await draw());if(results[0].historyEligible||results.slice(1).some(x=>x.reason!=='static'))throw Error('static history contract');return results;}'''
CUT='''async ()=>{const {draw,options,span}=window.__vaporTemporal;const eye=options.eye.slice();eye[0]+=.03*span;const small=await draw({eye});if(!small.historyEligible)throw Error('small camera motion rejected');const opposite=options.eye.map((v,i)=>2*options.target[i]-v);const cut=await draw({eye:opposite});if(cut.historyEligible||cut.reason!=='camera-cut')throw Error('camera cut reused history');await draw();return {small,cut};}'''
DIAGNOSTICS='''async ()=>{const {e,draw}=window.__vaporTemporal;const before=e.simulation.readbackStats;if(before.allocations||before.completed||before.bytesCopied)throw Error('unexpected render readback');const metrics=await e.simulation.metrics(),atlas=await e.atlasRGBA8();let max=0;for(let i=0;i<atlas.length;i+=4)max=Math.max(max,atlas[i]);if(metrics.nonFinite!==0||!(metrics.densityIntegral>0)||max===0)throw Error('empty or nonfinite field');return {metrics,maxDensityByte:max,atlasBytes:atlas.length,renderReadback:before,explicitReadback:e.simulation.readbackStats};}'''
RESET='''async ()=>{const {e,draw}=window.__vaporTemporal;e.reset();const result=await draw();if(result.historyEligible||result.reason!=='field-reset')throw Error('reset reused history');return result;}'''
CLOSE='''()=>{const s=window.__vaporTemporal;if(s){s.temporal.dispose();s.direct.dispose();s.ctx.unconfigure();s.e.dispose();delete window.__vaporTemporal;}}'''

def compare(a,b):
    from PIL import Image,ImageChops
    with Image.open(a) as ia,Image.open(b) as ib:
        if ia.size!=ib.size:raise RuntimeError('capture dimensions mismatch')
        diff=ImageChops.difference(ia.convert('RGB'),ib.convert('RGB'));p=list(diff.getdata());n=len(p)
        return {'pixels':n,'changed_gt2':sum(max(v)>2 for v in p),'rgb_mse':sum(sum(x*x for x in v) for v in p)/(3*n)}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--modes',nargs='+',choices=['gpu','hybrid'],default=['gpu']);p.add_argument('--presets',nargs='+',choices=['cigarette_smoke','exhaled_aerosol','steam','smoke','flame'],default=['cigarette_smoke','exhaled_aerosol']);p.add_argument('--frames',type=int,default=48);p.add_argument('--channel',choices=['chrome','msedge']);p.add_argument('--browser');p.add_argument('--headless',action='store_true');p.add_argument('--allow-software',action='store_true');p.add_argument('--timeout',type=int,default=180000);a=p.parse_args()
    if not 24<=a.frames<=120 or a.timeout<1000:p.error('frames 24..120 and timeout >= 1000 required')
    if a.channel and a.browser:p.error('choose channel or browser, not both')
    modes=list(dict.fromkeys(a.modes));keys=list(dict.fromkeys(a.presets));out=ROOT/'reports/local/webgpu-temporal';out.mkdir(parents=True,exist_ok=True);report_path=out/'validation.json'
    names=[f'{mode}-{key}-{phase}.png' for mode in modes for key in keys for phase in PHASES];clear_previous_outputs(out,['validation.json',*names]);report={'schema':'vapor.webgpu-temporal-validation/1','sdk_version':'0.16.0','status':'IN_PROGRESS','complete':False,'evidence':'Real browser WebGPU simulation and temporal rendering; no native engine capture. MSE descriptive; not a runtime FPS benchmark.','modes':modes,'presets':keys,'allow_software':a.allow_software,'checks':[]};atomic_report(report_path,report);code=2
    try:
        if 'hybrid' in modes:report['wasm_receipt']=require_receipt(ROOT/'bindings/web/vapor.wasm')
        from playwright.sync_api import sync_playwright
        from PIL import Image
        class Handler(http.server.SimpleHTTPRequestHandler):
            def log_message(self,*args):pass
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(ROOT)));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as pw:
                launch={'headless':a.headless}
                if a.channel:launch['channel']=a.channel
                if a.browser:launch['executable_path']=a.browser
                browser=pw.chromium.launch(**launch)
                try:
                    for mode in modes:
                        for key in keys:
                            row={'mode':mode,'preset':key,'status':'FAIL'};page=browser.new_page(viewport={'width':1280,'height':900},device_scale_factor=1);page.set_default_timeout(a.timeout);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                            paths={phase:out/f'{mode}-{key}-{phase}.png' for phase in PHASES}
                            def capture(phase):
                                page.locator('#canvas').screenshot(path=str(paths[phase]));
                                with Image.open(paths[phase]) as im:
                                    if im.size!=(320,200):raise RuntimeError(f'wrong capture size: {im.size}')
                            try:
                                page.goto(f'http://127.0.0.1:{server.server_port}/examples/webgpu-volume/',timeout=a.timeout)
                                row['initial']=page.evaluate(INIT,{'mode':mode,'key':key,'allowSoftware':a.allow_software,'width':320,'height':200});capture('blank')
                                row['active']=page.evaluate(ACTIVE,a.frames);capture('active')
                                page.evaluate("()=>window.__vaporTemporal.draw({kind:'direct'})");capture('direct-low')
                                row['static']=page.evaluate(STATIC);capture('temporal-static')
                                page.evaluate("()=>window.__vaporTemporal.draw({kind:'direct',steps:192})");capture('reference-high')
                                row['camera']=page.evaluate(CUT);row['diagnostics']=page.evaluate(DIAGNOSTICS);row['reset']=page.evaluate(RESET);capture('reset')
                                row['blank_active']=compare(paths['blank'],paths['active']);row['blank_reset']=compare(paths['blank'],paths['reset'])
                                if row['blank_active']['changed_gt2']<8:raise RuntimeError('active image visually indistinguishable from blank')
                                if row['blank_reset']['changed_gt2']>8:raise RuntimeError('reset image differs from blank')
                                row['reference_comparison']={k:compare(paths[k],paths['reference-high']) for k in ('direct-low','temporal-static')}
                                if errors:raise RuntimeError(str(errors))
                                row.update(status='PASS',images=[{'file':f.name,'sha256':sha256(f)} for f in paths.values()])
                            except Exception as e:
                                row.update(error=str(e),traceback=traceback.format_exc());row['status']='BLOCKED' if any(s in str(e) for s in ('ERR_BLOCKED_BY_ADMINISTRATOR','WebGPU is unavailable','No WebGPU compute adapter','WebGPU canvas unavailable')) else 'FAIL'
                            finally:
                                try:page.evaluate(CLOSE)
                                except Exception:pass
                                page.close();report['checks'].append(row);atomic_report(report_path,report);print(row['status'],mode,key,flush=True)
                finally:browser.close()
        finally:server.shutdown();server.server_close();thread.join(5)
        report['status']='PASS' if report['checks'] and all(r['status']=='PASS' for r in report['checks']) else 'BLOCKED' if report['checks'] and all(r['status']=='BLOCKED' for r in report['checks']) else 'FAIL';code={'PASS':0,'FAIL':1,'BLOCKED':2}[report['status']]
    except Exception as e:
        report['error']=str(e);report['status']='BLOCKED' if isinstance(e,(ImportError,FileNotFoundError,OSError)) or 'Executable doesn\'t exist' in str(e) else 'FAIL';code=2 if report['status']=='BLOCKED' else 1
    report['complete']=True;atomic_report(report_path,report);print(report['status'],report_path);return code
if __name__=='__main__':raise SystemExit(main())
