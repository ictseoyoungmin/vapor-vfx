#!/usr/bin/env python3
"""Actual native time-series, plume geometry and host-side timing; no fixture fallback.
GPU step time is host submission time, not synchronized GPU execution or game FPS.
"""
from __future__ import annotations
import argparse,json,math,os,shutil,subprocess,sys,time,traceback
from pathlib import Path
from runtime_common import ROOT,default_library,require_receipt,sha256,source_fingerprint
from quality_metrics import density_summary,atlas_summary,timing_summary
from capture_atlas import capture_atlas
from capture_float import capture_float
from capture_fidelity import capture_fidelity
sys.path.insert(0,str(ROOT/'bindings/python'))
from vapor_game import create_effect
MODES={'cpu':1,'gpu':2,'hybrid':3}
KEYS=['cigarette_smoke','exhaled_aerosol','steam','smoke','flame']

def checkpoint_ticks(seconds,dt):
    if not math.isfinite(dt) or dt<=0 or not seconds or any(not math.isfinite(t) or t<=0 or t>30 for t in seconds):raise ValueError('sample times must be finite in (0,30]')
    return sorted(set(max(1,round(t/dt)) for t in seconds))

def run_case(key,mode,quality,args,out):
    options={'backend':mode,'quality':quality,'library':args.library,'detail_scale':1 if mode=='cpu' else (args.detail_scale or (2 if mode=='hybrid' else 1)),'detail_turbulence':0. if mode=='cpu' else args.detail_turbulence,'detail_frequency':8. if mode=='cpu' else args.detail_frequency,'allow_software_gpu':args.allow_software and mode!='cpu'}
    with create_effect(key,**options) as effect:
        sim=effect.runtime;info=effect.backend_info
        if info['active']!=MODES[mode] or info['flags']&8 or (not args.allow_software and info['flags']&32):raise RuntimeError(f'wrong execution backend: {info}')
        c=sim.config;cells=[c[k] for k in ['nx','ny','nz']];extent=[n*c['cell_size'] for n in cells];dt=c['fixed_dt'];origin=c['origin'];em=effect.emitter
        axes=dict(origin=origin,source=em['position'],direction=em['direction']);ticks=checkpoint_ticks(args.samples,dt)
        emit_seconds=args.emit_seconds if args.emit_seconds is not None else (effect.definition['profile'] or {}).get('duration',2.2)
        stop_tick=max(1,round(emit_seconds/dt));sample_ticks=sorted(set(ticks+[stop_tick]) & set(range(1,max(ticks)+1)))
        snapshots=[];step_ms=[];since=[];effect.play();start=time.perf_counter();last_sync=start;stopped=False
        for tick in range(1,max(ticks)+1):
            t=time.perf_counter_ns();r=effect.advance(dt);ms=(time.perf_counter_ns()-t)/1e6
            if not r or r['steps']!=1 or r['dropped_seconds']>1e-9:raise RuntimeError(f'fixed-step control mismatch at {tick}: {r}')
            step_ms.append(ms);since.append(ms)
            if tick==stop_tick:effect.stop();stopped=True
            if tick not in sample_ticks:continue
            t=time.perf_counter();atlas=effect.atlas_rgba8();after_atlas=time.perf_counter()
            m=sim.metrics();rho=sim.field('density',numpy=True);after_diag=time.perf_counter()
            if m['ticks']!=tick or m['non_finite']!=0 or not math.isfinite(m['density_integral']):raise RuntimeError(f'invalid runtime state at tick {tick}')
            coarse=density_summary(rho,cells=cells,extent=extent,cap=c['density_cap'],**axes)
            render=atlas_summary(atlas,cells=list(info['render_cells']),extent=extent,density_cap=c['density_cap'],**axes)
            if abs(coarse['density_integral']-m['density_integral'])>max(1e-9,abs(m['density_integral'])*1e-5):raise RuntimeError('native density integral differs from actual coarse field')
            row={'tick':tick,'simulated_seconds':m['time'],'source_removed':stopped,'metrics':m,'coarse':coarse,'render':render,'atlas_sha256':__import__('hashlib').sha256(atlas).hexdigest(),'timing':{'step_host_since_last_sample':timing_summary(since),'sync_atlas_copy_ms':(after_atlas-t)*1000,'metrics_and_coarse_copy_ms':(after_diag-after_atlas)*1000,'wall_since_previous_sample_end_ms':(after_diag-last_sync)*1000}}
            since=[]
            if args.capture and render['occupied_voxels']:
                row['capture']=capture_atlas(atlas,cells=list(info['render_cells']),extent=extent,density_cap=c['density_cap'],material=effect.definition['material'],path=out/f'{mode}-{quality}-{key}-tick{tick:04d}.png')
            elif args.capture:row['capture']={'status':'EMPTY','note':'No quantized density, no misleading placeholder image.'}
            if args.capture_float and coarse['density_integral']>0:
                temperature=sim.field('temperature',numpy=True)
                row['coarse_float_capture']=capture_float(rho,temperature,cells=cells,extent=extent,density_cap=c['density_cap'],material=effect.definition['material'],path=out/f'{mode}-{quality}-{key}-tick{tick:04d}-float.png')
            elif args.capture_float:row['coarse_float_capture']={'status':'EMPTY','note':'No positive coarse density'}
            if args.capture_fidelity and coarse['density_integral']>0:
                temperature=sim.field('temperature',numpy=True)
                row['coarse_fidelity_capture']=capture_fidelity(rho,temperature,effect=key,cells=cells,extent=extent,density_cap=c['density_cap'],material=effect.definition['material'],path=out/f'{mode}-{quality}-{key}-tick{tick:04d}-fidelity.png')
            elif args.capture_fidelity:row['coarse_fidelity_capture']={'status':'EMPTY','note':'No positive coarse density'}
            snapshots.append(row);last_sync=time.perf_counter()
        if not any(row['coarse']['density_integral']>0 for row in snapshots):raise RuntimeError('no emission detected in sampled coarse field')
        if not any(row['render']['occupied_voxels']>0 for row in snapshots):raise RuntimeError('no visible density detected in sampled render atlas')
        return {'key':key,'mode':mode,'quality':quality,'backend':info,'config':c,'source_stop_tick':stop_tick,'step_host':timing_summary(step_ms),'total_case_wall_ms_including_diagnostics_and_optional_capture':(time.perf_counter()-start)*1000,'snapshots':snapshots}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',action='store_true');p.add_argument('--modes',nargs='+',choices=list(MODES),default=['cpu']);p.add_argument('--effects',nargs='+',choices=KEYS,default=KEYS[:2]);p.add_argument('--quality',choices=['low','medium','high'],default='low');p.add_argument('--samples',nargs='+',type=float,default=[.25,.5,1.,2.,3.,4.]);p.add_argument('--emit-seconds',type=float);p.add_argument('--capture',action='store_true');p.add_argument('--capture-float',action='store_true',help='compare actual coarse Float32 field with its RGBA8 encoding (Node + NumPy)');p.add_argument('--capture-fidelity',action='store_true',help='render actual native coarse Float32 field with opt-in CPU fidelity renderer');p.add_argument('--detail-scale',type=int,choices=[1,2,3,4],help='native GPU/Hybrid scalar scale (CPU always 1)');p.add_argument('--detail-turbulence',type=float,default=0.,help='existing native GPU detail force, NOT the independent reference candidate');p.add_argument('--detail-frequency',type=float,default=8.);p.add_argument('--allow-software',action='store_true');p.add_argument('--library',type=Path,default=default_library());args=p.parse_args()
    if not math.isfinite(args.detail_turbulence) or not 0<=args.detail_turbulence<=2 or not math.isfinite(args.detail_frequency) or not .1<=args.detail_frequency<=100:p.error('invalid native detail controls')
    if args.detail_turbulence and 'gpu' in args.modes and (args.detail_scale or 1)==1:p.error('GPU detail turbulence requires detail scale > 1')
    try:checkpoint_ticks(args.samples,1/60)
    except ValueError as e:p.error(str(e))
    if args.emit_seconds is not None and (not math.isfinite(args.emit_seconds) or not 0<args.emit_seconds<=max(args.samples)):p.error('--emit-seconds must be positive and not exceed final sample')
    modes=list(dict.fromkeys(args.modes));keys=list(dict.fromkeys(args.effects));gpu=any(m!='cpu' for m in modes)
    out=ROOT/'reports/local'/('profile-'+'-'.join(modes));out.mkdir(parents=True,exist_ok=True)
    # Clear only owned evidence, including captures from previous sampling schedules.
    import re
    for path in out.iterdir():
        if path.is_file() and (path.name in ('validation.json','build.log','runtime-stderr.log') or re.fullmatch(r'(cpu|gpu|hybrid)-(low|medium|high)-(cigarette_smoke|exhaled_aerosol|steam|smoke|flame)-tick\d+(?:-float|-fidelity)?\.png',path.name)):path.unlink()
    report={'schema':'vapor.effect-timeline/1','status':'BLOCKED','modes':modes,'effects':keys,'quality':args.quality,'requested_samples_seconds':args.samples,'allow_software':args.allow_software,'requested_native_detail':{'scale':args.detail_scale,'turbulence':args.detail_turbulence,'frequency':args.detail_frequency,'cpu_always_scale_1':True},'source_fingerprint':source_fingerprint(),'timing_notice':'CPU host step includes compute. GPU/Hybrid host advance may only submit work; sync atlas copy includes queued work and transfer. Neither is engine frame time; diagnostics/captures excluded from host-step samples. Density integral is not physical aerosol mass.','cases':[]}
    code=2
    try:
        if args.build:
            if not shutil.which('cargo') or not shutil.which('rustc'):raise FileNotFoundError('cargo/rustc absent; no native run')
            with (out/'build.log').open('w') as log:
                r=subprocess.run([sys.executable,'tools/build.py','--native','--test']+(['--gpu'] if gpu else []),cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
            if r.returncode:raise RuntimeError(f'build failed ({r.returncode}), see build.log')
        report['receipt']=require_receipt(args.library,gpu=gpu);code=1
        # Capture native diagnostics from OS stderr (not only Python exceptions).
        os.environ['VAPOR_GPU_DIAGNOSTICS']='1'
        report['runtime_diagnostics_log']='runtime-stderr.log'
        with (out/'runtime-stderr.log').open('w',encoding='utf-8') as log:
            saved=os.dup(2)
            try:
                os.dup2(log.fileno(),2)
                for mode in modes:
                    for key in keys:
                        try:row={'status':'PASS','data':run_case(key,mode,args.quality,args,out)}
                        except Exception as e:row={'status':'FAIL','error':str(e),'traceback':traceback.format_exc()}
                        report['cases'].append(dict(mode=mode,key=key,**row));print(row['status'],mode,key,flush=True)
            finally:os.dup2(saved,2);os.close(saved)
        code=int(any(row['status']!='PASS' for row in report['cases']));report['status']='FAIL' if code else 'PASS'
    except FileNotFoundError as e:report.update(status='BLOCKED',error=str(e));code=2
    except Exception as e:report.update(status='FAIL',error=str(e));code=1
    finally:
        (out/'validation.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');print(report['status'],out/'validation.json',flush=True)
    return code
if __name__=='__main__':raise SystemExit(main())
