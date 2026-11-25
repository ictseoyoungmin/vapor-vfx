#!/usr/bin/env python3
"""Browser smoke for the real hosted CPU cloud; never a native/GPU benchmark."""
from functools import partial
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from threading import Thread
import argparse
from playwright.sync_api import sync_playwright

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--site',type=Path,default=Path('dist/pages'))
    ap.add_argument('--output',type=Path,default=Path('reports/local/interactive-cloud'))
    args=ap.parse_args()
    assert (args.site/'examples/interactive-cloud/index.html').is_file(), 'build Pages first'
    args.output.mkdir(parents=True,exist_ok=True)
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(SimpleHTTPRequestHandler,directory=str(args.site.resolve())))
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            page=browser.new_page(viewport={'width':1280,'height':900},device_scale_factor=1)
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(f'http://127.0.0.1:{server.server_port}/examples/interactive-cloud/')
            ready=page.locator('#status[data-ready=true]')
            ready.wait_for(timeout=120000)
            assert page.locator('#status').get_attribute('data-field-builds')=='1'
            before=page.locator('#canvas').evaluate('(c)=>c.toDataURL()')
            rect=page.locator('#canvas').bounding_box();assert rect
            x,y=rect['x']+rect['width']/2,rect['y']+rect['height']/2
            page.mouse.move(x,y);page.mouse.down();page.mouse.move(x+120,y+35,steps=6);page.mouse.up()
            ready.wait_for(timeout=120000)
            after=page.locator('#canvas').evaluate('(c)=>c.toDataURL()')
            assert before!=after
            assert page.locator('#status').get_attribute('data-cache-builds')=='1'
            page.screenshot(path=str(args.output/'orbit.png'),full_page=True)
            page.mouse.move(x,y);page.mouse.wheel(0,-100);page.wait_for_timeout(300)
            ready.wait_for(timeout=120000)
            assert page.locator('#canvas').evaluate('(c)=>c.toDataURL()')!=after
            page.select_option('#light','back');ready.wait_for(timeout=120000)
            assert page.locator('#status').get_attribute('data-cache-builds')=='2'
            page.select_option('#light','original');ready.wait_for(timeout=120000)
            page.click('#reset');ready.wait_for(timeout=120000)
            assert page.locator('#canvas').evaluate('(c)=>c.toDataURL()')==before
            page.screenshot(path=str(args.output/'canonical.png'),full_page=True)
            # Actual downloadable, independent GLBs and source VPF1 from the hosted worker.
            import json, struct
            page.click('#bake')
            page.locator('#bake-result a').nth(3).wait_for(timeout=120000)
            assert page.locator('#bake-result a').count()==4
            counts=[]
            for i in range(4):
                with page.expect_download() as info:
                    page.locator('#bake-result a').nth(i).click()
                download=info.value
                data=download.path().read_bytes()
                if i<3:
                    assert download.suggested_filename==f'vapor-cloud-lod{i}.glb'
                    assert struct.unpack_from('<III',data)==(0x46546c67,2,len(data))
                    size,kind=struct.unpack_from('<II',data,12)
                    assert kind==0x4e4f534a
                    doc=json.loads(data[20:20+size])
                    assert doc['meshes'][0]['extras']['vapor']['resolution']==128//(2**i)
                    assert doc['materials'][0]['pbrMetallicRoughness']['metallicFactor']==0
                    counts.append(doc['accessors'][2]['count']//3)
                else:
                    assert download.suggested_filename=='vapor-cloud-source.vpf'
                    assert data[:4]==b'VPF1'
                    assert struct.unpack_from('<III',data,8)==(96,48,64)
            assert counts[0]>counts[1]>counts[2]
            assert page.locator('#canvas').evaluate('(c)=>c.toDataURL()')==before
            page.screenshot(path=str(args.output/'cloud-bake.png'),full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert not errors, errors
            page.set_viewport_size({'width':1280,'height':900})
            page.goto(f'http://127.0.0.1:{server.server_port}/examples/terrain-fog/')
            ready=page.locator('#status[data-ready=true]')
            ready.wait_for(timeout=120000)
            assert int(page.locator('#status').get_attribute('data-visible-pixels')) > 100
            before=page.locator('#canvas').evaluate('(c)=>c.toDataURL()')
            page.screenshot(path=str(args.output/'terrain-fog.png'),full_page=True)
            page.select_option('#view','oblique');page.click('#render');ready.wait_for(timeout=120000)
            assert page.locator('#canvas').evaluate('(c)=>c.toDataURL()')!=before
            assert page.locator('#status').get_attribute('data-cache-builds')=='1'
            page.select_option('#light','back');page.click('#render');ready.wait_for(timeout=120000)
            assert page.locator('#status').get_attribute('data-cache-builds')=='2'
            page.locator('#coverage').evaluate("(e)=>{e.value='0.8';e.dispatchEvent(new Event('input',{bubbles:true}));}")
            page.click('#render');ready.wait_for(timeout=120000)
            assert page.locator('#status').get_attribute('data-field-builds')=='2'
            page.click('#reset');ready.wait_for(timeout=120000)
            assert page.locator('#canvas').evaluate('(c)=>c.toDataURL()')==before
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)
    print('PASS browser: cloud and terrain fog, controls, reset, cache reuse, mobile bounds')
if __name__=='__main__':main()
