#!/usr/bin/env python3
"""Full-scene parity. Reference is actual JS; candidate requires receipt-bound Rust."""
from __future__ import annotations
import argparse,array,json,math,subprocess,sys,time
from pathlib import Path
from runtime_common import ROOT,default_library,require_receipt,sha256,source_fingerprint,clear_previous_outputs
from check_sdk import atomic_report
from png_codec import write_rgba
sys.path.insert(0,str(ROOT/'bindings/python'))
from vapor_game.fidelity import FidelityCPU,Fields

def read_f32(p):
    a=array.array('f');a.frombytes(p.read_bytes())
    if sys.byteorder!='little':a.byteswap()
    return a

def compare(a,b,atol,rtol=0):
    if len(a)!=len(b) or not len(a):raise ValueError('invalid comparison size')
    mx=ss=0.;bad=0
    for x,y in zip(a,b):
        if not math.isfinite(x) or not math.isfinite(y):raise ValueError('nonfinite field/image')
        d=abs(x-y);mx=max(mx,d);ss+=d*d;bad+=d>atol+rtol*abs(y)
    return dict(count=len(a),max_abs=mx,rmse=math.sqrt(ss/len(a)),violations=bad,passed=bad==0)

def native_options(scene,spec):
    m=dict(scene['material']);m['thermal_fade']=m.pop('thermalFade');l=scene['lighting'];c=scene['camera']
    return dict(eye=c['eye'],target=c['target'],width=spec['width'],height=spec['height'],steps=spec['steps'],fov=c['fov'],exposure=c['exposure'],jitter=c['jitter'],dark=c['background']=='dark',material=m,lighting=dict(direction=l['light']['direction'],radiance=l['light']['radiance'],sky=l['sky'],ground=l['ground'],multi_scatter=l['multiScatter'],shadow_steps=l['shadowSteps'],light_scale=l['lightScale']))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--profile',choices=['preview','hero'],default='preview');p.add_argument('--build',action='store_true');p.add_argument('--reference-only',action='store_true');p.add_argument('--output',type=Path,default=ROOT/'reports/local/cloud-equivalence');a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    clear_previous_outputs(out,['reference.png','rust.png','rust-density.f32','rust-temperature.f32','rust-alpha.f32','validation.json','build.log','reference.log']);ref=out/'reference';ref.mkdir(exist_ok=True);clear_previous_outputs(ref,['reference.json','density.f32','temperature.f32','alpha.f32','frame.rgba'])
    scene_path=ROOT/'contracts/cloud-hero.json';scene=json.loads(scene_path.read_text());s=scene['profiles'][a.profile];tol=scene['tolerances'];report=dict(schema='vapor.cloud-equivalence/1',status='RUNNING',complete=False,profile=a.profile,scene_sha256=sha256(scene_path),source_fingerprint=source_fingerprint(),reference_status='NOT_RUN',rust_status='NOT_RUN',production_release_ready=False);rp=out/'validation.json';atomic_report(rp,report)
    try:
        with (out/'reference.log').open('w') as log:subprocess.run(['node',str(ROOT/'tools/cloud_reference.mjs'),a.profile,str(ref)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=900)
        m=json.loads((ref/'reference.json').read_text())
        if set(m['files'])!={'density.f32','temperature.f32','alpha.f32','frame.rgba'}:raise RuntimeError('missing reference files')
        for name,info in m['files'].items():
            if sha256(ref/name)!=info['sha256'] or (ref/name).stat().st_size!=info['bytes']:raise RuntimeError('reference checksum mismatch')
        d=read_f32(ref/'density.f32');t=read_f32(ref/'temperature.f32');alpha=read_f32(ref/'alpha.f32');rgba=(ref/'frame.rgba').read_bytes()
        if len(d)!=math.prod(s['cells']) or len(t)!=len(d) or len(alpha)!=s['width']*s['height'] or not any(x>.001 for x in alpha):raise RuntimeError('invalid/empty reference')
        write_rgba(out/'reference.png',s['width'],s['height'],rgba);report.update(reference_status='PASS',reference=m,reference_png_sha256=sha256(out/'reference.png'));atomic_report(rp,report)
        if a.reference_only:report.update(status='REFERENCE_ONLY',complete=True,rust_status='NOT_RUN');atomic_report(rp,report);return 0
        if a.build:
            with (out/'build.log').open('w') as log:r=subprocess.run([sys.executable,str(ROOT/'tools/build.py'),'--native','--test'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=1800)
            if r.returncode==2:raise FileNotFoundError('actual Rust toolchain not available')
            if r.returncode:raise RuntimeError('native build/test failed; see build.log')
        report['receipt']=require_receipt(default_library());sdk=FidelityCPU(default_library());start=time.perf_counter();v=sdk.generate(scene['preset'],quality=scene['quality'],cells=s['cells'],extent=scene['extent'],settings=scene['settings'],time=scene['time']);report['generation_ms']=(time.perf_counter()-start)*1000
        opts=native_options(scene,s);start=time.perf_counter();pixels,actual_alpha=sdk.render(v,**opts);report['render_ms']=(time.perf_counter()-start)*1000
        for name,values in [('density',v.density),('temperature',v.temperature),('alpha',actual_alpha)]:
            ar=array.array('f',values)
            if sys.byteorder!='little':ar.byteswap()
            (out/f'rust-{name}.f32').write_bytes(ar.tobytes())
        write_rgba(out/'rust.png',s['width'],s['height'],pixels)
        op,oa=sdk.render(Fields(tuple(s['cells']),tuple(scene['extent']),m['densityCap'],d,t),**opts)
        results={'density':compare(v.density,d,tol['density_atol'],tol['density_rtol']),'temperature':compare(v.temperature,t,0),'isolated_alpha':compare(oa,alpha,tol['alpha_atol'],tol['alpha_rtol']),'isolated_rgba':compare(op,rgba,tol['rgba_max_error']),'end_to_end_alpha':compare(actual_alpha,alpha,tol['alpha_atol'],tol['alpha_rtol']),'end_to_end_rgba':compare(pixels,rgba,tol['rgba_max_error'])}
        ok=all(x['passed'] for x in results.values());report.update(status='PASS' if ok else 'FAIL',rust_status='PASS' if ok else 'FAIL',comparison=results,rust_png_sha256=sha256(out/'rust.png'),complete=True);code=0 if ok else 1
    except FileNotFoundError as e:report.update(status='BLOCKED',rust_status='BLOCKED',reason=str(e),complete=True);code=2
    except Exception as e:report.update(status='FAIL',rust_status='FAIL',reason=str(e),complete=True);code=1
    atomic_report(rp,report);print(report['status'],rp);return code
if __name__=='__main__':raise SystemExit(main())
