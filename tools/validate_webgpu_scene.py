#!/usr/bin/env python3
"""Real WebGPU scene-depth shader validation: analytic buffer + actual GPU/Hybrid fluid.
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
 const e=await createEffect(key,{quality:'low',execution:{backend:mode,detailScale:mode==='hybrid'?2:1,allowSoftwareGpu:allowSoftware}});
 const device=e.simulation.renderSource().device,w=161,h=101,row=Math.ceil(w*4/256)*256,bg=[.1,.2,.3],width=w,height=h;
 let target,depth,staging,analyticBuffer,analytic,direct;
 const errors=[];const onError=x=>errors.push(String(x.error?.message??x.error));device.addEventListener('uncapturederror',onError);
 try{
  if(e.backend!==mode||e.simulation.backendInfo.initFallback)throw Error('unexpected backend');
  target=device.createTexture({size:[w,h,1],format:'rgba8unorm',usage:GPUTextureUsage.RENDER_ATTACHMENT|GPUTextureUsage.COPY_SRC});
  depth=device.createTexture({size:[w,h,1],format:'r32float',usage:GPUTextureUsage.TEXTURE_BINDING|GPUTextureUsage.COPY_DST});
  staging=device.createBuffer({size:row*h,usage:GPUBufferUsage.COPY_DST|GPUBufferUsage.MAP_READ});
  const setDepth=distance=>{const data=new Float32Array(row/4*h);for(let y=0;y<h;y++)data.fill(distance,y*row/4,y*row/4+w);device.queue.writeTexture({texture:depth},data,{bytesPerRow:row,rowsPerImage:h},[w,h,1]);};
  const encode=a=>{let s='';for(let i=0;i<a.length;i+=8192)s+=String.fromCharCode(...a.subarray(i,i+8192));return btoa(s);};
  const draw=async(renderer,options,distance=null)=>{
   const v=target.createView(),encoder=device.createCommandEncoder(),pass=encoder.beginRenderPass({colorAttachments:[{view:v,loadOp:'clear',storeOp:'store',clearValue:{r:bg[0],g:bg[1],b:bg[2],a:1}}]});pass.end();device.queue.submit([encoder.finish()]);
   if(distance!==null)setDepth(distance);
   renderer.render(v,{...options,aspect:w/h,background:'transparent',load:true,...(distance===null?{}:{sceneDepth:depth,width,height})});
   const cp=device.createCommandEncoder();cp.copyTextureToBuffer({texture:target},{buffer:staging,bytesPerRow:row,rowsPerImage:h},[w,h,1]);device.queue.submit([cp.finish()]);await staging.mapAsync(GPUMapMode.READ);
   const src=new Uint8Array(staging.getMappedRange()),a=new Uint8Array(w*h*4);for(let y=0;y<h;y++)a.set(src.subarray(y*row,y*row+w*4),y*w*4);staging.unmap();return a;
  };
  const diff=(a,b)=>{let n=0;for(let i=0;i<a.length;i+=4)if(Math.max(...[0,1,2,3].map(c=>Math.abs(a[i+c]-b[i+c])))>1)n++;return n;};
  const centre=a=>[...a.subarray(((h>>1)*w+(w>>1))*4,((h>>1)*w+(w>>1))*4+4)];
  // Real shader on a known uniform Float32 field; not a solver run.
  analyticBuffer=device.createBuffer({size:64*16,usage:GPUBufferUsage.STORAGE|GPUBufferUsage.COPY_DST});const field=new Float32Array(64*4);for(let i=0;i<64;i++)field[i*4]=.6;device.queue.writeBuffer(analyticBuffer,0,field);
  analytic=await GpuVolumeRenderer.create({renderSource:()=>({device,buffer:analyticBuffer,layout:'detail',cells:[4,4,4],extent:[1,1,1],origin:[0,0,0]})},{format:'rgba8unorm',enableSceneDepth:true});
  const opts={eye:[.5,.5,-1],target:[.5,.5,.5],steps:64,shadowSteps:0,material:{colour:[1,1,1],extinction:1.3,anisotropy:0,albedo:1,ambient:1,emission:0,thermalFade:0}};
  const analyticRows=[];for(const [distance,length] of [[.5,0],[1.25,.25],[1.5,.5],[2,1],[0,1]]){const a=await draw(analytic,opts,distance),actual=centre(a),expected=bg.map(v=>Math.round(255*(1-Math.exp(-.6*1.3*length)+Math.exp(-.6*1.3*length)*Math.round(v*255)/255)));if(actual.slice(0,3).some((v,i)=>Math.abs(v-expected[i])>2)||actual[3]!==255)throw Error('analytic scene depth mismatch '+JSON.stringify({distance,actual,expected}));analyticRows.push({distance,length,actual,expected});}
  // Actual fluid field, same-device GPU/Hybrid direct draw.
  direct=await GpuVolumeRenderer.create(e.simulation,{format:'rgba8unorm',enableSceneDepth:true});const c=e.extent.map((v,i)=>v/2+e.config.origin[i]),span=Math.max(...e.extent),camera={eye:[c[0]+span*.5,c[1]+span*.15,c[2]-span*1.65],target:c,material:e.definition.material,steps:96,shadowSteps:6};
  const blank=await draw(direct,camera,0);e.play();for(let i=0;i<90;i++){e.advance(e.config.fixedDt);if(i%8===7)await device.queue.onSubmittedWorkDone();}
  const active=await draw(direct,camera,null),zero=await draw(direct,camera,0),front=await draw(direct,camera,.000001),behind=await draw(direct,camera,1e7);
  const changes={active:diff(active,blank),zeroVsDirect:diff(zero,active),frontVsBlank:diff(front,blank),behindVsDirect:diff(behind,active)};
  if(changes.active<8||changes.zeroVsDirect||changes.frontVsBlank||changes.behindVsDirect)throw Error('actual fluid scene depth comparison failed '+JSON.stringify(changes));
  const readback=e.simulation.readbackStats;if(readback.allocations||readback.completed||readback.bytesCopied)throw Error('renderer unexpectedly read back solver field');await device.queue.onSubmittedWorkDone();if(errors.length)throw Error(errors.join('\\n'));
  return {width:w,height:h,analyticRows,changes,backend:e.backend,adapter:e.simulation.backendInfo,solverReadback:readback,images:{blank:encode(blank),active:encode(active),front:encode(front),behind:encode(behind)}};
 }finally{device.removeEventListener('uncapturederror',onError);analytic?.dispose();direct?.dispose();analyticBuffer?.destroy();target?.destroy();depth?.destroy();staging?.destroy();e.dispose();}
}'''

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--modes',nargs='+',choices=['gpu','hybrid'],default=['gpu']);p.add_argument('--preset',choices=['cigarette_smoke','exhaled_aerosol','steam','smoke','flame'],default='exhaled_aerosol');p.add_argument('--allow-software',action='store_true');p.add_argument('--headless',action='store_true');p.add_argument('--channel',choices=['chrome','msedge']);p.add_argument('--browser');p.add_argument('--timeout',type=int,default=180000);a=p.parse_args()
    if a.channel and a.browser:p.error('choose channel or browser, not both')
    modes=list(dict.fromkeys(a.modes));out=ROOT/'reports/local/webgpu-scene';out.mkdir(parents=True,exist_ok=True);clear_previous_outputs(out,['validation.json',*[f'{m}-{k}.png' for m in ('gpu','hybrid') for k in ('blank','active','front','behind')]])
    report={'schema':'vapor.webgpu-scene/1','sdk_version':json.loads((ROOT/'project.json').read_text())['sdk_version'],'status':'IN_PROGRESS','complete':False,'modes':modes,'preset':a.preset,'allow_software':a.allow_software,'checks':[],'evidence':'Real GPU shader analytic buffer test and actual fluid computation; offscreen target readback only, not game FPS or engine screenshot'};rp=out/'validation.json';atomic_report(rp,report)
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
