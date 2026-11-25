#!/usr/bin/env python3
"""Actual Studio browser screenshots of the three CPU procedural presets. No WASM required."""
import argparse,functools,http.server,json,threading
from pathlib import Path
from runtime_common import ROOT,sha256,clear_previous_outputs

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--browser');p.add_argument('--timeout',type=int,default=120000);args=p.parse_args();out=ROOT/'reports/local/studio-captures';out.mkdir(parents=True,exist_ok=True)
    keys=['cumulus_cloud','ground_fog','dust'];clear_previous_outputs(out,['captures.json']+[k+'.png' for k in keys]);report={'status':'BLOCKED','captures':[],'evidence':'Actual browser Studio CPU procedural path; not fluid or GPU rendering'};code=2
    try:
        from playwright.sync_api import sync_playwright
        class Handler(http.server.SimpleHTTPRequestHandler):
            def log_message(self,*args):pass
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(ROOT)));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(**({'executable_path':args.browser} if args.browser else {}))
                try:
                    for key in keys:
                        page=browser.new_page(viewport={'width':1280,'height':860},device_scale_factor=1);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                        page.goto(f'http://127.0.0.1:{server.server_port}/examples/effects-studio/?effect={key}',timeout=args.timeout)
                        page.wait_for_function("['PASS','FAIL'].includes(window.__VAPOR_EFFECT_CAPTURE__?.status)",timeout=args.timeout);d=page.evaluate('window.__VAPOR_EFFECT_CAPTURE__')
                        if d['status']!='PASS' or d['effect']!=key or d['backend']!='procedural-cpu' or d['occupied']<=0 or errors:raise RuntimeError(str({'data':d,'errors':errors}))
                        file=out/(key+'.png');page.screenshot(path=str(file));report['captures'].append({'file':file.name,'sha256':sha256(file),'runtime':d});page.close()
                finally:browser.close()
        finally:server.shutdown();server.server_close();thread.join(5)
        report['status']='PASS';code=0
    except Exception as e:
        report['error']=str(e);report['status']='BLOCKED' if isinstance(e,ImportError) or 'ERR_BLOCKED_BY_ADMINISTRATOR' in str(e) or 'Executable doesn\'t exist' in str(e) or isinstance(e,OSError) else 'FAIL';code=2 if report['status']=='BLOCKED' else 1
    (out/'captures.json').write_text(json.dumps(report,indent=2)+'\n');print(report['status'],out);return code
if __name__=='__main__':raise SystemExit(main())
