#!/usr/bin/env python3
"""Actual receipt-bound Rust optical rendering of a baked JS field (not Rust generation)."""
import argparse,hashlib,json,subprocess,sys,time
from pathlib import Path
from runtime_common import ROOT,default_library,require_receipt,source_fingerprint,sha256,clear_previous_outputs
from check_sdk import atomic_report
from validate_cloud_equivalence import native_options,compare
from png_codec import write_rgba
sys.path.insert(0,str(ROOT/'bindings/python'))
from vapor_game.field_asset import read_field_asset,encode_field_asset
from vapor_game.fidelity import FidelityCPU

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('asset_dir',type=Path);p.add_argument('--build',action='store_true');p.add_argument('--output',type=Path,default=ROOT/'reports/local/baked-cloud-native');a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    if a.asset_dir.resolve()==out: p.error('output must be separate from assets')
    clear_previous_outputs(out,['rust.png','validation.json','build.log']);rp=out/'validation.json'
    r=dict(schema='vapor.baked-cloud-native/1',status='RUNNING',complete=False,source_fingerprint=source_fingerprint(),scope='Python VPF1 decode + actual Rust optical renderer; NOT Rust generation or GPU',production_release_ready=False);atomic_report(rp,r)
    try:
        from PIL import Image
        root=a.asset_dir;meta=json.loads((root/'cloud.json').read_text());scene=json.loads((ROOT/'contracts/cloud-hero.json').read_text());field=read_field_asset(root/'cloud.vpf');raw=encode_field_asset(field)
        if hashlib.sha256(raw).hexdigest()!=meta['sha256'] or sha256(root/'cloud.vpf')!=meta['sha256']:raise ValueError('asset hash mismatch')
        if tuple(meta['cells'])!=field.cells or tuple(meta['extent'])!=field.extent or meta['densityCap']!=field.density_cap or meta['time']!=field.time:raise ValueError('field metadata mismatch')
        s=next((v for v in scene['profiles'].values() if tuple(v['cells'])==field.cells),None)
        if not s or field.extent!=tuple(scene['extent']) or field.time!=scene['time'] or meta['material']!=scene['material'] or meta['lighting']!=scene['lighting'] or meta['camera']!={**scene['camera'],'width':s['width'],'height':s['height'],'steps':s['steps']}:raise ValueError('not the canonical baked cloud scene')
        with Image.open(root/'cloud.png') as im:
            if im.size!=(s['width'],s['height']):raise ValueError('reference size mismatch')
            rgba=im.convert('RGBA').tobytes()
        if hashlib.sha256(rgba).hexdigest()!=meta['rgbaSha256']:raise ValueError('reference RGBA checksum mismatch')
        r.update(asset_status='PASS',asset_sha256=meta['sha256'],reference_rgba_sha256=meta['rgbaSha256']);atomic_report(rp,r)
        if a.build:
            with (out/'build.log').open('w') as log:res=subprocess.run([sys.executable,str(ROOT/'tools/build.py'),'--native','--test'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=1800)
            if res.returncode==2:raise FileNotFoundError('actual Rust toolchain not available')
            if res.returncode:raise RuntimeError('native build/test failed; see build.log')
        r['receipt']=require_receipt(default_library());sdk=FidelityCPU(default_library());start=time.perf_counter();pixels,_=sdk.render(field.native_fields(),**native_options(scene,s));r['render_ms']=(time.perf_counter()-start)*1000
        write_rgba(out/'rust.png',s['width'],s['height'],pixels);m=compare(pixels,rgba,scene['tolerances']['rgba_max_error']);r.update(comparison=m,status='PASS' if m['passed'] else 'FAIL',complete=True);rc=0 if m['passed'] else 1
    except FileNotFoundError as e:r.update(status='BLOCKED',reason=str(e),complete=True);rc=2
    except Exception as e:r.update(status='FAIL',reason=str(e),complete=True);rc=1
    atomic_report(rp,r);print(r['status'],rp);return rc
if __name__=='__main__':raise SystemExit(main())
