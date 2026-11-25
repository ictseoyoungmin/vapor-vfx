#!/usr/bin/env python3
"""Capture v18 WebGL2 metrics from actual Chromium; never overwrite original baseline.

Examples:
  python3 tools/capture_webgl_baseline.py --smoke-frames 0 --output reports/smoke.json
  python3 tools/capture_webgl_baseline.py --marks 0.5,1,2,3 --output reports/low_new.json
Playwright Python is optional and required only for this dynamic tool.
"""
import argparse
import contextlib
import datetime as dt
import functools
import http.server
import json
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT/'history/legacy/v18'
class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args): pass
@contextlib.contextmanager
def server():
    srv=http.server.ThreadingHTTPServer(('127.0.0.1', 0),functools.partial(QuietHandler,directory=str(LEGACY)))
    th=threading.Thread(target=srv.serve_forever,daemon=True);th.start()
    try: yield srv.server_port
    finally: srv.shutdown(); srv.server_close(); th.join(timeout=3)

def run(args):
    from playwright.sync_api import sync_playwright
    marks=[] if args.smoke_frames is not None else [float(x) for x in args.marks.split(',')]
    if marks and (marks!=sorted(set(marks)) or any(x<0 for x in marks)):
        raise ValueError('marks must be unique, increasing and nonnegative')
    page_errors=[]
    start=time.monotonic()
    with server() as port, sync_playwright() as p:
        opt={'headless':True,'args':['--no-sandbox','--disable-dev-shm-usage','--use-angle=swiftshader','--use-gl=angle',
                                      '--enable-unsafe-swiftshader','--ignore-gpu-blocklist','--enable-webgl']}
        if args.chromium: opt['executable_path']=str(args.chromium)
        browser=p.chromium.launch(**opt)
        try:
            page=browser.new_page(viewport={'width':640,'height':480},device_scale_factor=1)
            page.set_default_timeout(args.timeout*1000)
            page.on('pageerror',lambda e:page_errors.append(str(e)))
            page.goto(f'http://127.0.0.1:{port}/index.html?test=1&q={args.quality}&fresh=1',wait_until='domcontentloaded',timeout=args.timeout*1000)
            page.wait_for_function('window.__vaporReady === true',timeout=args.timeout*1000)
            gpu=page.evaluate('window.__vapor.report().gpu')
            if args.smoke_frames is not None:
                if args.smoke_frames: page.evaluate('(n)=>window.__vapor.advance(n)',args.smoke_frames)
                metrics=page.evaluate('window.__vapor.metrics()') if args.smoke_frames else None
                record={'schema':'vapor.webgl-smoke/1','frames':args.smoke_frames,'metrics_after_frames':metrics}
            else:
                page.evaluate('() => {const V=window.__vapor; V.director.auto=false; V.director.style="cloud"; V.setPhase("exhale",0);}')
                prev=0; samples=[]
                for m in marks:
                    n=round((m-prev)*60)
                    page.evaluate('(n)=>window.__vapor.advance(n)',n)
                    sample=page.evaluate('window.__vapor.metrics()')
                    samples.append({'t':m,'m':sample})
                    print('CAPTURE',m,n,'mass',sample.get('mass'),flush=True)
                    prev=m
                bench=page.evaluate('(s)=>window.__vapor.evalBench(s)',samples)
                record={'schema':'vapor.webgl-metrics/1','marks':marks,'samples':samples,'bench':bench}
            if args.screenshot:
                args.screenshot.parent.mkdir(parents=True,exist_ok=True)
                page.evaluate('window.__vapor.draw()')
                page.screenshot(path=str(args.screenshot))
            record.update({'quality':args.quality,'gpu':gpu,'browser':browser.version,
                           'captured_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
                           'elapsed_wall_seconds':round(time.monotonic()-start,2),
                           'page_errors':page_errors,
                           'status':'ok' if not page_errors else 'page_errors'})
        finally: browser.close()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('SAVED',args.output,record['status'],flush=True)
    return 0 if record['status']=='ok' else 1

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--smoke-frames',type=int)
    ap.add_argument('--marks',default='0.5,1,2,3')
    ap.add_argument('--quality',choices=('low','mid','high','ultra'),default='low')
    ap.add_argument('--chromium',type=Path)
    ap.add_argument('--timeout',type=int,default=120)
    ap.add_argument('--screenshot',type=Path)
    ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args()
    if a.smoke_frames is not None and a.smoke_frames<0: ap.error('negative frames')
    try: exit(run(a))
    except Exception as e:
        print('CAPTURE FAILED',type(e).__name__,str(e)[:1200],flush=True)
        exit(1)
