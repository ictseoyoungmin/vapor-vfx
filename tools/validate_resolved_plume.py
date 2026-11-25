#!/usr/bin/env python3
"""Build/run only the real Rust resolved-plume example; no Lab fallback.
Results use a fresh run directory, source fingerprint and per-file hashes.
A successful short probe is not full M2 or visual/game approval.
"""
from __future__ import annotations
import argparse,csv,math,shutil,subprocess,sys,tempfile,time
from pathlib import Path
from runtime_common import ROOT,sha256,source_fingerprint
from build import cpu_workspace
from check_sdk import atomic_report
from png_codec import write_rgba

MODES=['legacy_source','matched','seeded']
EFFECTS={'cigarette_smoke':1,'exhaled_aerosol':2}

def convert_ppm(path):
    raw=path.read_bytes();magic,dim,maxval,pixels=raw.split(b'\n',3);w,h=map(int,dim.split())
    if magic!=b'P6' or maxval!=b'255' or not 1<=w<=1600 or not 1<=h<=1600 or len(pixels)!=w*h*3:raise ValueError('invalid Rust PPM capture')
    rgba=bytearray(w*h*4);rgba[0::4]=pixels[0::3];rgba[1::4]=pixels[1::3];rgba[2::4]=pixels[2::3];rgba[3::4]=b'\xff'*(w*h)
    out=path.with_suffix('.png');write_rgba(out,w,h,rgba);return out

def check_metrics(path,expected_ticks):
    with path.open(newline='') as f:rows=list(csv.DictReader(f))
    if len(rows)!=expected_ticks or [int(r['tick']) for r in rows]!=list(range(1,expected_ticks+1)):raise ValueError('missing Rust time steps')
    for r in rows:
        values=[float(v) for k,v in r.items() if k not in ('effect','mode')]
        if not all(math.isfinite(v) for v in values):raise ValueError('nonfinite runtime metric')
        initial=float(r['cg_initial_rms']);residual=float(r['cg_residual_rms'])
        if residual>max(initial*1e-4,1e-5):raise ValueError('CG pressure gate failed')
        # Check the projected velocity, not just solved pressure.
        if float(r['divergence_rms'])>max(initial*2e-4,2e-5):raise ValueError('post-projection divergence gate failed')
        if int(r['clamps']):raise ValueError('velocity clamp invalidates resolved flow comparison')
    inj=sum(float(r['injected']) for r in rows);out=sum(float(r['outflow']) for r in rows);dec=sum(float(r['decayed']) for r in rows);sat=sum(float(r['saturated']) for r in rows);final=float(rows[-1]['density_integral']);err=final-(inj-out-dec-sat)
    if inj<=0 or abs(err)>max(1e-10,1e-6*inj):raise ValueError('aggregate density closure failed')
    return dict(ticks=len(rows),max_divergence=max(float(r['divergence_rms']) for r in rows),max_cg_iterations=max(int(r['cg_iterations']) for r in rows),injected=inj,outflow_fraction=out/inj,relative_budget_residual=err/inj,final_integral=final,full_plume_capture_eligible=out/inj<=0.05)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--effects',nargs='+',choices=EFFECTS,default=list(EFFECTS));p.add_argument('--models',nargs='+',choices=MODES,default=MODES);p.add_argument('--seconds',type=float,default=4.);p.add_argument('--timeout',type=int,default=3600,help='per-case seconds');p.add_argument('--output',type=Path,default=ROOT/'reports/local/native-resolved');a=p.parse_args()
    if not math.isfinite(a.seconds) or not .25<=a.seconds<=4 or a.timeout<1:p.error('seconds .25..4 and positive timeout required')
    if len(set(a.effects))!=len(a.effects) or len(set(a.models))!=len(a.models):p.error('duplicate effect/model')
    a.output=a.output.resolve();a.output.mkdir(parents=True,exist_ok=True);out=Path(tempfile.mkdtemp(prefix='run-',dir=a.output));path=out/'validation.json';report=dict(schema='vapor.native-resolved/1',status='RUNNING',complete=False,source_fingerprint=source_fingerprint(),effects=a.effects,models=a.models,seconds=a.seconds,rows=[],visual_acceptance='REQUIRED',production_release_ready=False);atomic_report(path,report);print(out,flush=True)
    if not shutil.which('cargo') or not shutil.which('rustc'):
        report.update(status='BLOCKED',complete=True,reason='cargo/rustc absent; no Rust execution/captures');atomic_report(path,report);return 2
    try:
        report['rustc']=subprocess.check_output(['rustc','--version'],text=True).strip();manifest=cpu_workspace()
        for effect in a.effects:
            for model in a.models:
                case=out/(effect+'-'+model);case.mkdir();log=case/'runtime.log';cmd=['cargo','run','--release','--offline','--manifest-path',str(manifest),'--target-dir',str(ROOT/'target/cpu'),'-p','vapor-core','--example','m2_resolved','--',str(case),str(EFFECTS[effect]),model,str(a.seconds)]
                row=dict(effect=effect,model=model,command=cmd,status='RUNNING');report['rows'].append(row);atomic_report(path,report)
                try:
                    with log.open('w',encoding='utf-8') as f:r=subprocess.run(cmd,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,timeout=a.timeout)
                    if r.returncode:raise RuntimeError(f'Rust process failed ({r.returncode}): {log}')
                    row['metrics']=check_metrics(case/'metrics.csv',math.floor(a.seconds*120+.5));files=sorted(case.glob('*.ppm'))
                    if len(files)!=4:raise ValueError('missing runtime render snapshots')
                    for f in files:convert_ppm(f)
                    row.update(status='PASS_EXECUTION_ONLY',files={f.name:sha256(f) for f in sorted(case.iterdir()) if f.is_file()})
                    atomic_report(path,report)
                except BaseException as e:row.update(status='FAIL',error=str(e));raise
        report.update(status='PASS_EXECUTION_ONLY',complete=True);atomic_report(path,report);return 0
    except BaseException as e:report.update(status='FAIL',complete=True,reason=str(e));atomic_report(path,report);return 1
if __name__=='__main__':raise SystemExit(main())
