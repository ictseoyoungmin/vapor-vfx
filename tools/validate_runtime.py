#!/usr/bin/env python3
"""Actual native CPU/GPU/Hybrid acceptance run; no fixture or silent CPU substitution.

Examples:
  python tools/validate_runtime.py --build --modes cpu --capture
  python tools/validate_runtime.py --build --modes gpu hybrid --capture
  python tools/validate_runtime.py --modes cpu gpu hybrid --frames 600

GPU unit/WGSL validation runs on the CPU during --build. Actual GPU runtime uses
an explicit device; --allow-software is opt-in and recorded, never a hardware PASS.
"""
from __future__ import annotations
import argparse,ctypes,datetime,hashlib,json,math,os,platform,shutil,statistics,subprocess,sys,time,traceback
from pathlib import Path
from runtime_common import ROOT,default_library,require_receipt,source_fingerprint,clear_previous_outputs
from png_codec import write_rgba,composite_linear_premultiplied
sys.path.insert(0,str(ROOT/'bindings/python'))
from vapor_game import Simulation,VaporError

BASE=dict(cells=(12,16,12),cell_size=.05,pressure_iterations=80,max_velocity=2.,vorticity=.1)
EMITTER=dict(position=(.30,.10,.30),direction=(.12,1.,.08),radius=.075,length=.09,
             speed=.65,density_rate=12.,temperature=1.2)
MODES={'cpu':1,'gpu':2,'hybrid':3}

def finite_tree(value):
    if isinstance(value,float):return math.isfinite(value)
    if isinstance(value,dict):return all(finite_tree(x) for x in value.values())
    if isinstance(value,(list,tuple)):return all(finite_tree(x) for x in value)
    return True

def digest(values)->str:return hashlib.sha256(bytes(values)).hexdigest()

def checked_fields(sim):
    fields={name:sim.field(name) for name in ['density','temperature','pressure','solid','velocity']}
    assert all(all(math.isfinite(x) for x in values) for values in fields.values()),'non-finite field'
    assert all(0<=x<=sim.config['density_cap']+1e-5 for x in fields['density']),'density outside bounds'
    assert all(x in (0.,1.) for x in fields['solid']),'solid mask is not binary'
    assert all(rho==0 for rho,solid in zip(fields['density'],fields['solid']) if solid>.5),'density in solid cells'
    return fields

def scene(sim):
    sim.set_emitter(0,**EMITTER)
    sim.set_sphere(0,(.30,.37,.30),.09)

def parity(a,b):
    assert len(a)==len(b),'field lengths differ'
    max_abs=max((abs(x-y) for x,y in zip(a,b)),default=0.)
    rmse=math.sqrt(sum((x-y)**2 for x,y in zip(a,b))/max(1,len(a)))
    worst=max((abs(x-y)/(.003+.002*max(abs(x),abs(y))) for x,y in zip(a,b)),default=0.)
    return {'max_abs':max_abs,'rmse':rmse,'max_tolerance_ratio':worst,'passed':worst<=1.}

def run_mode(mode,library,allow_software,frames,capture,out)->dict:
    options=dict(library=library,backend=mode,detail_scale=2 if mode=='hybrid' else 1,
                 allow_software_gpu=allow_software)
    checks=[];metrics=[];captures=[];backend=None
    def record(name,fn):
        start=time.perf_counter()
        try:
            data=fn();checks.append({'name':name,'status':'PASS','seconds':time.perf_counter()-start,'data':data})
        except Exception as e:
            checks.append({'name':name,'status':'FAIL','seconds':time.perf_counter()-start,
                           'error':str(e),'traceback':traceback.format_exc()})
    try:
        with Simulation(**BASE,**options) as sim:
            backend=sim.backend_info
            assert backend['active']==MODES[mode],f'wrong active backend: {backend}'
            assert not backend['flags']&8,'CPU fallback forbidden in acceptance run'
            if not allow_software:assert not backend['flags']&32,'software adapter requires explicit --allow-software'
            assert backend['render_cells']==[n*options['detail_scale'] for n in BASE['cells']]
            def empty():
                sim.step(8);m=sim.metrics();checked_fields(sim)
                assert m['density_integral']==0 and m['max_speed']==0 and m['non_finite']==0
                sim.reset();return m
            record('empty_domain',empty)
            def profile():
                sim.reset();sim.set_emitter(0,**EMITTER)
                sim.set_profile(0,[(0.,1.,1.,1.),(1.,1.,1.,1.)],duration=.4,start_time=.1)
                sim.step(3);assert sim.metrics()['density_integral']==0,'profile emitted before start'
                sim.step(12);assert sim.metrics()['density_integral']>0,'profile failed to emit'
                sim.set_profile(0,None);sim.reset();return {'delayed_start':True}
            record('profile_start_and_clear',profile)
            def compare():
                sim.reset();scene(sim);sim.step(8);candidate=checked_fields(sim)
                with Simulation(**BASE,library=library,backend='cpu') as reference:
                    scene(reference);reference.step(8);reference_fields=checked_fields(reference)
                diffs={key:parity(reference_fields[key],candidate[key]) for key in reference_fields}
                assert all(row['passed'] for row in diffs.values()),json.dumps(diffs)
                if mode in ('cpu','hybrid'):
                    assert all(bytes(reference_fields[k])==bytes(candidate[k]) for k in reference_fields), 'CPU authoritative coarse physics differ'
                return {'horizon_steps':8,'tolerance':'abs <= 0.003 + 0.002*max(abs(CPU),abs(candidate))',
                        'differences':diffs,'note':'Short-horizon gate only, not long-horizon turbulent equivalence'}
            record('short_horizon_cpu_reference',compare)
            def lifecycle():
                sim.reset();scene(sim);sim.step(16);before=bytes(sim.field('density'))
                sim.reset();assert sim.metrics()['ticks']==0
                assert sim.metrics()['density_integral']==0
                sim.step(16);after=bytes(sim.field('density'))
                assert before==after,'same-device reset/replay is not deterministic'
                return {'density_sha256':hashlib.sha256(before).hexdigest()}
            record('reset_replay_determinism',lifecycle)
            def clock():
                sim.reset();r=sim.advance(1.)
                assert r['steps']==sim.config['max_substeps'] and r['dropped_seconds']>0
                assert abs(r['steps']*sim.config['fixed_dt']+r['dropped_seconds']+r['alpha']*sim.config['fixed_dt']-1.)<1e-6
                t=sim.metrics()['ticks']
                for seconds in (-1.,float('nan'),float('inf')):
                    try:sim.advance(seconds)
                    except (VaporError,ValueError):pass
                    else:raise AssertionError('invalid elapsed accepted')
                assert sim.metrics()['ticks']==t
                return r
            record('clock_hitch_and_invalid_input',clock)
            def moving_obstacle():
                sim.reset();scene(sim)
                for i in range(12):
                    sim.set_sphere(0,(.24+.008*i,.35,.30),.09,velocity=(.48,0.,0.))
                    sim.step(1);checked_fields(sim)
                sim.remove_obstacle(0);sim.step(1)
                assert not any(sim.field('solid'))
                return {'updates':12,'cleared_mask':True}
            record('moving_obstacle_and_remove',moving_obstacle)
            def ticketed_atlas():
                sim.reset();scene(sim);sim.step(8)
                start=time.perf_counter();expected=sim.atlas_rgba8();sync_ms=(time.perf_counter()-start)*1000
                assert any(expected[::4]),'submission snapshot empty'
                start=time.perf_counter();ticket=sim.begin_atlas();begin_ms=(time.perf_counter()-start)*1000
                assert ticket is not None and ticket.ticks==8 and ticket.bytes==len(expected)
                assert sim.begin_atlas() is None,'busy slot accepted a second request'
                sim.step(2)
                # Also exercise the separate legacy staging path while a ticket is outstanding.
                later=sim.atlas_rgba8();assert len(later)==len(expected)
                polls=[];deadline=time.monotonic()+35
                while True:
                    t=time.perf_counter();data=sim.poll_atlas(ticket);polls.append((time.perf_counter()-t)*1000)
                    if data is not None:break
                    assert time.monotonic()<deadline,'ticket never completed';time.sleep(.001)
                assert data==expected,'atlas is not the submission tick snapshot'
                def stale(t):
                    try:sim.poll_atlas(t)
                    except VaporError as e:assert e.code==-2,e
                    else:raise AssertionError('stale ticket accepted')
                stale(ticket);cancel=sim.begin_atlas();assert cancel is not None and cancel.id>ticket.id;sim.cancel_atlas(cancel);stale(cancel)
                reset=sim.begin_atlas();assert reset is not None and reset.id>cancel.id;sim.reset();stale(reset)
                final=sim.begin_atlas();assert final is not None and final.id>reset.id and final.ticks==0
                deadline=time.monotonic()+35
                while True:
                    cleared=sim.poll_atlas(final)
                    if cleared is not None:break
                    assert time.monotonic()<deadline;time.sleep(.001)
                assert not any(cleared[::4]) and all(x==255 for x in cleared[3::4]),'reset atlas not empty'
                return {'submission_ticks':ticket.ticks,'later_ticks':10,'sha256':digest(data),'bytes':len(data),
                        'sync_copy_ms':sync_ms,'begin_host_ms':begin_ms,'poll_host_ms_max':max(polls),'poll_calls':len(polls),
                        'cancel_reset_reuse':True,'timing_scope':'host call timing only; later blocking snapshot is intentional correctness test, not a frame-rate benchmark'}
            record('ticketed_atlas_snapshot_and_lifecycle',ticketed_atlas)
            def plume():
                sim.reset();scene(sim);submitted=[];snapshot=[]
                start=time.perf_counter();left=frames
                while left:
                    n=min(12,left);t=time.perf_counter();sim.step(n)
                    submitted.append((time.perf_counter()-t)*1000/n)
                    t=time.perf_counter();m=sim.metrics();atlas=sim.atlas_rgba8()
                    snapshot.append((time.perf_counter()-t)*1000)
                    assert finite_tree(m) and m['non_finite']==0 and m['clamped_velocities']==0,m
                    assert len(atlas)==math.prod(backend['render_cells'])*4
                    assert all(v==255 for v in atlas[3::4])
                    metrics.append(m);left-=n
                synchronized_ms=(time.perf_counter()-start)*1000
                fields=checked_fields(sim)
                assert m['ticks']==frames and m['density_integral']>0,m
                assert any(v>0 for v in atlas[::4]),'atlas contains no density'
                if capture:
                    raw=sim.render(eye=(1.05,.63,1.15),target=(.30,.36,.30),width=512,height=384,steps=112,extinction=18.)
                    assert any(raw[3::4]),'empty runtime preview'
                    path=out/f'{mode}-runtime-coarse.png'
                    write_rgba(path,512,384,composite_linear_premultiplied(raw))
                    captures.append({'path':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                                     'ticks':m['ticks'],'backend':mode,'renderer':'actual Rust CPU preview renderer',
                                     'field':'coarse physical field (not the high-resolution hybrid detail field)',
                                     'not':'Not Unity/Godot/Unreal editor or hardware render capture'})
                return {'steps':frames,'density_sha256':digest(fields['density']),
                        'step_call_ms_median':statistics.median(submitted),
                        'step_call_note':'GPU/Hybrid step calls enqueue work; these are NOT GPU execution times',
                        'readback_metrics_atlas_ms_median':statistics.median(snapshot),
                        'synchronized_total_ms':synchronized_ms,
                        'synchronized_ms_per_simulated_step':synchronized_ms/frames,
                        'timing_scope':'includes synchronization, Python boundary, diagnostic/atlas transfer; NOT game FPS',
                        'final_metrics':m}
            record('sustained_plume',plume)
            def cooldown():
                before=sim.metrics()['max_density'];sim.remove_emitter(0);sim.step(60)
                m=sim.metrics();checked_fields(sim)
                assert m['max_density']<=before+1e-5,'density grew with no source'
                return m
            record('source_removal_cooldown',cooldown)
            if mode != 'cpu':
                def fine_curl():
                    # Two real native runtimes, same coarse physics and fine grid.
                    # Closed domain and a solid sphere exercise fine wall/predictor handling.
                    cfg=dict(BASE,boundary=1);common=dict(library=library,backend=mode,detail_scale=3,detail_frequency=70.,allow_software_gpu=allow_software)
                    atlases=[];coarse=[];rows=[]
                    for amp in (0.,.3):
                        with Simulation(**cfg,**common,detail_turbulence=amp) as fine:
                            assert fine.backend_info['active']==MODES[mode] and not fine.backend_info['flags']&8
                            scene(fine);fine.step(48);m=fine.metrics();f=checked_fields(fine);atlas=fine.atlas_rgba8()
                            assert finite_tree(m) and m['non_finite']==0 and len(atlas)==math.prod(fine.backend_info['render_cells'])*4
                            assert any(atlas[::4]) and any(atlas[2::4]),'empty fine field or obstacle mask'
                            assert all(atlas[i]==0 for i in range(0,len(atlas),4) if atlas[i+2]==255),'density in solid fine voxels'
                            atlases.append(atlas);coarse.append(f);rows.append({'amplitude':amp,'atlas_sha256':digest(atlas),'cells':fine.backend_info['render_cells']})
                            fine.reset();cleared=fine.atlas_rgba8();assert not any(cleared[::4]),'fine reset left density'
                    assert atlases[0]!=atlases[1],'fine curl failed to change quantized output'
                    diffs={key:parity(coarse[0][key],coarse[1][key]) for key in coarse[0]}
                    assert all(d['passed'] for d in diffs.values()),'fine model changed coarse physics'
                    if mode=='hybrid':assert all(bytes(coarse[0][k])==bytes(coarse[1][k]) for k in coarse[0]),'Hybrid coarse field differs'
                    return {'fine_outputs':rows,'coarse_diffs':diffs,'closed_domain_obstacle_and_reset':True,'evidence':'actual native fine RGBA8 output; Float32 fine comparison via separate WebGPU validator'}
                record('fine_curl_isolation_closed_obstacle',fine_curl)

    except Exception as e:
        checks.append({'name':'create_or_close','status':'FAIL','error':str(e),'traceback':traceback.format_exc()})
    return {'mode':mode,'backend_info':backend,'status':'PASS' if checks and all(x['status']=='PASS' for x in checks) else 'FAIL',
            'checks':checks,'metrics_samples':metrics,'captures':captures}

def main()->int:
    if not __debug__:raise SystemExit("Validation requires assertions; do not run Python with -O")
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--modes',nargs='+',choices=list(MODES),default=['cpu'])
    ap.add_argument('--build',action='store_true');ap.add_argument('--allow-software',action='store_true')
    ap.add_argument('--capture',action='store_true');ap.add_argument('--frames',type=int,default=240)
    ap.add_argument('--output',type=Path,default=None);args=ap.parse_args()
    if not 24<=args.frames<=3600:ap.error('--frames must be 24..3600')
    modes=list(dict.fromkeys(args.modes));gpu=any(m!='cpu' for m in modes)
    out=(args.output or ROOT/'reports/local'/('gpu-hybrid' if gpu else 'cpu')).resolve();out.mkdir(parents=True,exist_ok=True)
    clear_previous_outputs(out,['build.log','runtime-stderr.log','validation.json']+[f'{mode}-runtime-coarse.png' for mode in MODES])
    report={'schema':'vapor.native-runtime-validation/1','sdk_version':json.loads((ROOT/'project.json').read_text())['sdk_version'],
            'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'host':platform.platform(),'python':sys.version,'modes_requested':modes,
            'software_adapter_allowed':args.allow_software,'source_fingerprint':source_fingerprint(),
            'status':'BLOCKED','build':{'status':'NOT_RUN'},'results':[],
            'production_release_ready':False,'note':'Passing this suite is not all-engine or original-v18 parity certification.'}
    exitcode=2
    try:
        if args.build:
            command=[sys.executable,str(ROOT/'tools/build.py'),'--native','--test']+(['--gpu'] if gpu else [])
            env={**os.environ,'VAPOR_ALLOW_SOFTWARE_GPU':'1' if args.allow_software else '0','VAPOR_GPU_DIAGNOSTICS':'1'}
            with (out/'build.log').open('w',encoding='utf-8') as log:
                process=subprocess.run(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
            report['build']={'status':'PASS' if process.returncode==0 else 'BLOCKED' if process.returncode==2 else 'FAIL',
                             'command':command,'returncode':process.returncode,'log':'build.log'}
            if process.returncode:raise RuntimeError(f'Build did not pass; inspect {out / "build.log"}')
        library=default_library();report['build_receipt']=require_receipt(library,gpu=gpu)
        os.environ['VAPOR_GPU_DIAGNOSTICS']='1'
        # Capture Rust/wgpu diagnostics (eprintln uses OS stderr, not Python's object).
        report['runtime_diagnostics_log']='runtime-stderr.log'
        with (out/'runtime-stderr.log').open('w',encoding='utf-8') as diagnostics:
            saved_stderr=os.dup(2)
            try:
                os.dup2(diagnostics.fileno(),2)
                for mode in modes:
                    result=run_mode(mode,library,args.allow_software,args.frames,args.capture,out)
                    report['results'].append(result);print(mode,result['status'],flush=True)
            finally:
                os.dup2(saved_stderr,2);os.close(saved_stderr)
        report['status']='PASS' if all(r['status']=='PASS' for r in report['results']) else 'FAIL'
        report['actual_runtime_test_count']=sum(len(r['checks']) for r in report['results'])
        exitcode=0 if report['status']=='PASS' else 1
    except Exception as e:
        report['error']=str(e)
        # A real build/runtime failure, stale receipt or invalid state is not a
        # missing-tool BLOCKED result. Only explicit missing prerequisites are.
        build_status=report['build']['status']
        if build_status=='BLOCKED' or (build_status=='NOT_RUN' and isinstance(e,FileNotFoundError)):
            report['status']='BLOCKED';exitcode=2
        else:
            report['status']='FAIL';exitcode=1
    finally:
        path=out/'validation.json';path.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
        print(report['status'],path,flush=True)
    return exitcode
if __name__=='__main__':raise SystemExit(main())
