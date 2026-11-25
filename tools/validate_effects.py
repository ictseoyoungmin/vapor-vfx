#!/usr/bin/env python3
"""Actual native preset smoke test, CPU procedural parity and optional actual field capture.
No fallback to JS or test double. Run validate_runtime.py separately for full solver gates.
"""
import argparse, json, math, shutil, subprocess, sys, time, traceback
from runtime_common import ROOT, default_library, require_receipt, clear_previous_outputs, sha256
from png_codec import write_rgba, composite_linear_premultiplied
from capture_atlas import capture_atlas
sys.path.insert(0,str(ROOT/'bindings/python'))
from vapor_game import create_effect
MODES={'cpu':1,'gpu':2,'hybrid':3}
KEYS=['cigarette_smoke','exhaled_aerosol','steam','smoke','flame']
def check_procedural(library):
    results=[]
    fixtures=json.loads((ROOT/'fixtures/effects-atlas-golden.json').read_text())['rows']
    for row in fixtures:
        with create_effect(row['key'],quality='low',library=library) as effect:
            effect.play();effect.advance(row['time']);a=effect.atlas_rgba8();assert len(a)==row['bytes']
            errors=[abs(a[i*4]-expected) for i,expected in row['samples']];total=sum(a[::4]);delta=abs(total-row['sum']);assert max(errors)<=1 and delta<=max(1,row['sum']*.005),(row['key'],row['time'],max(errors),delta)
            assert all(x==0 for x in a[1::4]) and all(x==0 for x in a[2::4]) and all(x==255 for x in a[3::4]);effect.reset();assert effect.time==0
            results.append(dict(key=row['key'],time=row['time'],max_byte_error=max(errors),sum_difference=delta))
    return results

def check_fluid(key,mode,library,allow_software,frames,capture,capture_detail,out):
    options={'detail_scale':2 if mode=='hybrid' else 1,'allow_software_gpu':allow_software}
    with create_effect(key,quality='low',library=library,backend=mode,**options) as effect:
        sim=effect.runtime;assert effect.backend_info['active']==MODES[mode];assert effect.backend==mode;assert not effect.backend_info['flags']&8
        if not allow_software:assert not effect.backend_info['flags']&32
        assert sim.metrics()['density_integral']==0;effect.play()
        start=time.perf_counter();sim.step(frames);m=sim.metrics();a=effect.atlas_rgba8();elapsed=time.perf_counter()-start
        assert m['ticks']==frames and m['non_finite']==0 and m['density_integral']>0 and math.isfinite(m['density_integral']);assert len(a)==math.prod(effect.render_shape)*4;assert any(a[::4]);assert all(math.isfinite(x) for x in sim.field('density'))
        row=dict(key=key,mode=mode,backend=effect.backend_info,metrics=m,atlas_bytes=len(a),atlas_sha256=__import__('hashlib').sha256(a).hexdigest(),wall_seconds=elapsed)
        if capture:
            c=sim.config;origin=c['origin'];extent=[c[k]*c['cell_size'] for k in ['nx','ny','nz']];center=[origin[i]+extent[i]/2 for i in range(3)];span=max(extent);eye=[center[0]+span*.6,center[1]+span*.2,center[2]-span*1.7];material=effect.definition['material'];width,height=320,240
            raw=sim.render(eye=eye,target=center,width=width,height=height,steps=64,extinction=material['extinction'],colour=material['colour']);assert any(raw[3::4]),'coarse preview empty';file=out/f'{mode}-{key}-coarse.png';write_rgba(file,width,height,composite_linear_premultiplied(raw));row['capture']={'file':file.name,'sha256':sha256(file),'evidence':'actual coarse fluid field CPU preview; not game renderer or ember mesh'}
        if capture_detail:
            c=sim.config;extent=[c[k]*c['cell_size'] for k in ['nx','ny','nz']]
            row['atlas_capture']=capture_atlas(a,cells=effect.backend_info['render_cells'],extent=extent,density_cap=c['density_cap'],material=effect.definition['material'],path=out/f'{mode}-{key}-atlas.png')
            row['atlas_capture'].update(backend=mode,ticks=m['ticks'],field='actual RGBA8 render atlas (includes Hybrid/GPU detail grid when enabled)',origin=c['origin'])
        effect.stop();effect.reset();assert sim.metrics()['density_integral']==0;return row

def main():
    if not __debug__:raise SystemExit("Validation requires assertions; do not run with python -O")
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',action='store_true');p.add_argument('--modes',nargs='+',choices=list(MODES),default=['cpu']);p.add_argument('--frames',type=int,default=48);p.add_argument('--capture',action='store_true',help='legacy coarse Rust preview');p.add_argument('--capture-atlas',action='store_true',help='Node CPU preview of actual full render atlas, fixed-domain + density detail views');p.add_argument('--allow-software',action='store_true');p.add_argument('--library',type=__import__('pathlib').Path,default=default_library());args=p.parse_args()
    if not 24<=args.frames<=240:p.error('--frames must be 24..240')
    modes=list(dict.fromkeys(args.modes));gpu=any(m!='cpu' for m in modes);out=ROOT/'reports/local'/('effects-'+'-'.join(modes));out.mkdir(parents=True,exist_ok=True)
    clear_previous_outputs(out,['validation.json','build.log']+[f'{m}-{key}-{kind}.png' for m in modes for key in KEYS for kind in ['coarse','atlas']]);report={'schema':'vapor.effects.runtime-validation/1','status':'BLOCKED','modes':modes,'allow_software':args.allow_software,'checks':[],'note':'Native Rust required. GPU/Hybrid actual selection checked. Procedural comparison uses independent JS fixture, never replaces native path.'}
    code=2
    try:
        if args.build:
            if not shutil.which('cargo') or not shutil.which('rustc'):raise FileNotFoundError('cargo/rustc absent; no native run')
            with (out/'build.log').open('w') as log:
                r=subprocess.run([sys.executable,'tools/build.py','--native','--test']+(['--gpu'] if gpu else []),cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
            if r.returncode:raise RuntimeError(f'build failed ({r.returncode}), see build.log')
        report['receipt']=require_receipt(args.library,gpu=gpu);code=1
        def record(name,fn):
            try:report['checks'].append({'name':name,'status':'PASS','data':fn()})
            except Exception as e:report['checks'].append({'name':name,'status':'FAIL','error':str(e),'traceback':traceback.format_exc()})
            print(report['checks'][-1]['status'],name,flush=True)
        record('procedural_rust_vs_js',lambda:check_procedural(args.library))
        for mode in modes:
            for key in KEYS:record(f'{mode}:{key}',lambda:check_fluid(key,mode,args.library,args.allow_software,args.frames,args.capture,args.capture_atlas,out))
        code=int(any(x['status']!='PASS' for x in report['checks']));report['status']='FAIL' if code else 'PASS'
    except FileNotFoundError as e:report.update(status='BLOCKED',error=str(e));code=2
    except Exception as e:report.update(status='FAIL',error=str(e));code=1
    finally:
        (out/'validation.json').write_text(json.dumps(report,indent=2)+'\n');print(report['status'],out/'validation.json')
    return code
if __name__=='__main__':raise SystemExit(main())
