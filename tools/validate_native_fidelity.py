"""Run the real Rust Fidelity C ABI against immutable JS fixtures; never substitute a backend."""
from __future__ import annotations
import argparse,ctypes as C,json,math,struct,subprocess,sys,time
from pathlib import Path
from runtime_common import ROOT,default_library,require_receipt,clear_previous_outputs,sha256
from check_sdk import atomic_report
from png_codec import write_rgba
sys.path.insert(0,str(ROOT/'bindings/python'))
from vapor_game.fidelity import FidelityCPU,Fields

def floats(p):
    b=p.read_bytes();return struct.unpack('<'+str(len(b)//4)+'f',b)
def check(a,b,atol,rtol,name):
    if len(a)!=len(b):raise RuntimeError(name+' length mismatch')
    err=0.
    for i,(x,y) in enumerate(zip(a,b)):
        if not math.isfinite(x) or not math.isfinite(y) or abs(x-y)>atol+rtol*abs(y):raise RuntimeError(f'{name} mismatch at {i}: {x} vs {y}')
        err=max(err,abs(x-y))
    return err

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',action='store_true');p.add_argument('--capture',action='store_true');p.add_argument('--output',type=Path,default=ROOT/'reports/local/native-fidelity');a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    fixture=ROOT/'fixtures/fidelity-port';m=json.loads((fixture/'manifest.json').read_text());clear_previous_outputs(out,['validation.json','build.log']+[x['id']+'.png' for x in m['cases']]);report={'schema':'vapor.native-fidelity/1','status':'BLOCKED','complete':False,'evidence':'Actual Rust library required, no JS/Python simulation fallback','rows':[]};atomic_report(out/'validation.json',report)
    try:
        for f in m['files']:
            if sha256(fixture/f['file'])!=f['sha256']:raise RuntimeError('fixture hash mismatch '+f['file'])
        if a.build:
            with (out/'build.log').open('w',encoding='utf-8') as log:r=subprocess.run([sys.executable,str(ROOT/'tools/build.py'),'--native','--test'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
            if r.returncode:
                report.update(status='BLOCKED' if r.returncode==2 else 'FAIL',complete=True,reason='Rust build or tests did not pass',build_returncode=r.returncode);atomic_report(out/'validation.json',report);return r.returncode
        report['receipt']=require_receipt(default_library());sdk=FidelityCPU(default_library());report['status']='RUNNING'
        for c in m['cases']:
            key=c['id'];e=c['extent'];terrain=floats(fixture/(key+'.terrain.f32')) if c['terrain'] else None
            start=time.perf_counter();f=sdk.generate(c['key'],cells=c['cells'],extent=e,time=c['time'],settings={k:c[k] for k in ['seed','coverage','humidity','erosion','wind']},terrain=terrain);gen=(time.perf_counter()-start)*1000
            d=floats(fixture/(key+'.density.f32'));t=floats(fixture/(key+'.temperature.f32'));de=check(f.density,d,2e-6,2e-6,'density');check(f.temperature,t,0,0,'temperature')
            # Test rendering with the exact reference fields to isolate optics.
            ref=Fields(tuple(c['cells']),tuple(e),1.,d,t);scene={}
            if c['terrain']:scene={'depth':floats(fixture/(key+'.depth.f32')),'radiance':floats(fixture/(key+'.scene.f32'))}
            opts=dict(eye=[e[0]*.65,e[1]*.22,-e[2]*1.5],target=[v*.5 for v in e],width=64,height=40,steps=48,fov=40,exposure=.95,lighting={'shadow_steps':12},**scene)
            start=time.perf_counter();pixels,alpha=sdk.render(ref,**opts);ms=(time.perf_counter()-start)*1000;ae=check(alpha,floats(fixture/(key+'.alpha.f32')),2e-5,2e-5,'alpha');pe=check(pixels,(fixture/(key+'.rgba')).read_bytes(),1,0,'RGBA')
            row=dict(case=key,max_density_abs_error=de,max_alpha_abs_error=ae,max_rgba_abs_error=pe,generation_ms=gen,render_ms=ms)
            if a.capture:
                # Real production data, not the fixture, at the same settings.
                actual,_=sdk.render(f,**opts);path=out/(key+'.png');write_rgba(path,64,40,actual);row['capture_sha256']=sha256(path)
            report['rows'].append(row);atomic_report(out/'validation.json',report)
        report.update(status='PASS',complete=True,production_release_ready=False);atomic_report(out/'validation.json',report);print('PASS actual Rust Fidelity C ABI');return 0
    except FileNotFoundError as e:
        report.update(status='BLOCKED',complete=True,reason=str(e));atomic_report(out/'validation.json',report);print('BLOCKED',e);return 2
    except Exception as e:
        report.update(status='FAIL',complete=True,reason=str(e));atomic_report(out/'validation.json',report);print('FAIL',e);return 1
if __name__=='__main__':raise SystemExit(main())
