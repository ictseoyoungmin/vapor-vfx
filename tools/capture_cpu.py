#!/usr/bin/env python3
"""Capture the REAL Rust WASM CPU Canvas example. Never creates a successful mock shot.

Requires: built bindings/web/vapor.wasm; pip install playwright; playwright install chromium.
No GPU or WebGL context is required. Use --browser /path/to/chromium for a local browser.
"""
from __future__ import annotations
import argparse,contextlib,functools,http.server,json,threading,sys
from pathlib import Path
from runtime_common import ROOT,require_receipt,sha256,clear_previous_outputs

def main()->int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--browser');ap.add_argument('--output',type=Path,default=ROOT/'reports/local/cpu-captures')
    args=ap.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    clear_previous_outputs(out,['captures.json','cpu-vent.png','cpu-wind.png','cpu-pulse.png'])
    report={'status':'BLOCKED','evidence':'Actual Rust WASM CPU simulation + Rust CPU preview + Canvas 2D application',
            'captures':[],'not':'Not a Unity/Godot/Unreal editor capture, not GPU performance evidence'}
    try:
        report['build_receipt']=require_receipt(ROOT/'bindings/web/vapor.wasm')
        from playwright.sync_api import sync_playwright
        class Handler(http.server.SimpleHTTPRequestHandler):
            def log_message(self,*args):pass
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(ROOT)))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as p:
                kwargs={'headless':True}
                if args.browser:kwargs['executable_path']=args.browser
                browser=p.chromium.launch(**kwargs)
                try:
                    for scenario in ['vent','wind','pulse']:
                        page=browser.new_page(viewport={'width':1280,'height':860},device_scale_factor=1)
                        errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                        page.goto(f'http://127.0.0.1:{server.server_port}/examples/cpu-canvas/?capture=1&scene={scenario}&steps=180')
                        page.wait_for_function("['PASS','FAIL'].includes(window.__VAPOR_CAPTURE__?.status)",timeout=240000)
                        data=page.evaluate('window.__VAPOR_CAPTURE__')
                        if data.get('status')!='PASS' or errors:raise RuntimeError(json.dumps({'runtime':data,'page_errors':errors}))
                        path=out/f'cpu-{scenario}.png';page.screenshot(path=str(path),full_page=True)
                        report['captures'].append({'path':path.name,'sha256':sha256(path),'runtime':data})
                        page.close()
                finally:browser.close()
        finally:server.shutdown();server.server_close();thread.join(timeout=5)
        report['status']='PASS';code=0
    except (ImportError,FileNotFoundError) as error:report['error']=str(error);code=2
    except Exception as error:report['status']='FAIL';report['error']=str(error);code=1
    (out/'captures.json').write_text(json.dumps(report,indent=2)+'\n');print(report['status'],out)
    return code
if __name__=='__main__':raise SystemExit(main())
