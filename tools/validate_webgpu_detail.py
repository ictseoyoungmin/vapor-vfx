#!/usr/bin/env python3
"""Actual GPU/Hybrid fine-curl shader and plume validation on the target PC.
Compiles production WGSL, probes its curl against independent CPU vectors, then
runs a real fine-field pair with curl off/on and captures actual GPU images.
"""
import argparse,base64,functools,http.server,json,threading,traceback
import numpy as np
from runtime_common import ROOT,require_receipt,sha256,clear_previous_outputs
from check_sdk import atomic_report
from detail_curl_math import curl
from png_codec import write_rgba

def fixtures():
    rng=np.random.default_rng(712);rows=[]
    for label,dx,scale,time,amp,k in [('resolved',.02,4,.77,.24,100),('wrap_before',.02,4,15.99,.24,100),('wrap_after',.02,4,16,.24,100),('unresolved',.16,2,.5,.24,100),('disabled',.02,4,.5,0,100)]:
        cells=[8,10,8];dims=np.array(cells)*scale;points=rng.uniform(0,1,(128,3))*dims
        for i in range(3):
            points[i,i]=0;points[3+i,i]=dims[i];points[6+i,i]=-.25;points[9+i,i]=dims[i]+.25
        points=points.astype(np.float32);fdx=float(np.float32(dx))/scale;actual=curl(points.astype(np.float64)*fdx,dims*fdx,k,amp,time,fdx)
        rows.append(dict(name=label,config=dict(cells=cells,cellSize=dx,maxVelocity=3),execution=dict(backend='gpu',detailScale=scale,detailTurbulence=amp,detailFrequency=k),time=time,points=points.tolist(),expected=actual.tolist()))
    return rows

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--modes',nargs='+',choices=['gpu','hybrid'],default=['gpu']);p.add_argument('--presets',nargs='+',choices=['cigarette_smoke','exhaled_aerosol'],default=['cigarette_smoke','exhaled_aerosol']);p.add_argument('--quality',choices=['low','medium','high'],default='low');p.add_argument('--frames',type=int,default=120);p.add_argument('--channel',choices=['chrome','msedge']);p.add_argument('--browser');p.add_argument('--headless',action='store_true');p.add_argument('--allow-software',action='store_true');p.add_argument('--timeout',type=int,default=240000);a=p.parse_args()
    if not 24<=a.frames<=240:p.error('frames 24..240')
    if a.channel and a.browser:p.error('choose channel or browser')
    modes=list(dict.fromkeys(a.modes));keys=list(dict.fromkeys(a.presets));out=ROOT/'reports/local/webgpu-detail';out.mkdir(parents=True,exist_ok=True);clear_previous_outputs(out,['validation.json',*[f'{m}-{k}-{v}.png' for m in modes for k in keys for v in ('blank','baseline','curl')]]);rp=out/'validation.json';report=dict(status='RUNNING',complete=False,evidence='actual production WGSL curl probes and real GPU/Hybrid fine scalar fields, actual Fidelity render-target capture; wall time is not GPU timestamp or FPS',shader_sha256=sha256(ROOT/'shaders/compute/detail.wgsl'),modes=modes,presets=keys,quality=a.quality,allow_software=a.allow_software,checks=[]);atomic_report(rp,report)
    try:
        if 'hybrid' in modes:report['wasm_receipt']=require_receipt(ROOT/'bindings/web/vapor.wasm')
        from playwright.sync_api import sync_playwright
        class Handler(http.server.SimpleHTTPRequestHandler):
            def log_message(self,*args):pass
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(ROOT)));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as pw:
                opts={'headless':a.headless}
                if a.channel:opts['channel']=a.channel
                if a.browser:opts['executable_path']=a.browser
                browser=pw.chromium.launch(**opts)
                try:
                    for mode in modes:
                        for key in keys:
                            page=browser.new_page();page.set_default_timeout(a.timeout);row=dict(mode=mode,key=key,status='FAIL')
                            try:
                                page.goto(f'http://127.0.0.1:{server.server_port}/examples/webgpu-volume/',timeout=a.timeout)
                                # JS timeout fails closed, including GPU hangs in page.evaluate.
                                result=page.evaluate('''async arg=>{const {runDetailValidation}=await import('/tools/webgpu_detail_probe.mjs');return await Promise.race([runDetailValidation(arg),new Promise((_,reject)=>setTimeout(()=>reject(Error('validation timed out')),arg.timeout))]);}''',dict(mode=mode,key=key,quality=a.quality,frames=a.frames,allowSoftware=a.allow_software,fixtures=fixtures(),timeout=a.timeout));images=result.pop('images');row.update(result);row['images']=[]
                                for name,encoded in images.items():
                                    path=out/f'{mode}-{key}-{name}.png';write_rgba(path,result['width'],result['height'],base64.b64decode(encoded));row['images'].append(dict(file=path.name,sha256=sha256(path)))
                                row['status']='PASS'
                            except Exception as e:
                                row.update(error=str(e),traceback=traceback.format_exc());row['status']='BLOCKED' if any(x in str(e) for x in ('ERR_BLOCKED_BY_ADMINISTRATOR','WebGPU is unavailable','No WebGPU compute adapter','Software GPU requires')) else 'FAIL'
                            finally:page.close();report['checks'].append(row);atomic_report(rp,report);print(row['status'],mode,key,flush=True)
                finally:browser.close()
        finally:server.shutdown();server.server_close();thread.join(5)
        statuses=[x['status'] for x in report['checks']];report['status']='PASS' if statuses and all(x=='PASS' for x in statuses) else 'BLOCKED' if statuses and all(x=='BLOCKED' for x in statuses) else 'FAIL'
    except Exception as e:
        report.update(error=str(e));report['status']='BLOCKED' if isinstance(e,(ImportError,FileNotFoundError,OSError)) or "Executable doesn't exist" in str(e) else 'FAIL'
    report['complete']=True;atomic_report(rp,report);print(report['status'],rp);return {'PASS':0,'FAIL':1,'BLOCKED':2}[report['status']]
if __name__=='__main__':raise SystemExit(main())
