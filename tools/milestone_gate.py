#!/usr/bin/env python3
"""Run representative real Rust M1/M2 gates. Never substitute the Lab.
M1 = native CPU and native Fidelity plus WASM parity, CPU captures.
M2 = actual integrated conservative density tests (run by build.py) and Rust A/B.
A pass is execution evidence, not automatic visual/game-release approval.
"""
import argparse,shutil,subprocess,sys,tempfile
from pathlib import Path
from runtime_common import ROOT,sha256,source_fingerprint
from check_sdk import atomic_report
from build import cpu_workspace

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--milestone',choices=['M1','M2','all'],default='all');p.add_argument('--quality',type=int,choices=[0,1,2],default=1);p.add_argument('--native-only',action='store_true',help='Explicitly omit WASM; cannot certify full M1');a=p.parse_args()
    base=ROOT/'reports/local/milestones';base.mkdir(parents=True,exist_ok=True)
    out=Path(tempfile.mkdtemp(prefix='run-',dir=base));path=out/'gate.json';report=dict(schema='vapor.milestone-gate/1',status='IN_PROGRESS',complete=False,source_fingerprint=source_fingerprint(),milestone=a.milestone,native_only=a.native_only,steps=[],production_release_ready=False)
    def save():atomic_report(path,report)
    def run(name,cmd):
        cmd=[str(v) for v in cmd];log=out/(name+'.log');row=dict(name=name,command=cmd,status='IN_PROGRESS');report['steps'].append(row);save()
        with log.open('w',encoding='utf-8') as f:
            try:r=subprocess.run(cmd,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,timeout=2400);code=r.returncode
            except (OSError,subprocess.TimeoutExpired) as exc:f.write(str(exc));code=1
        row.update(status='PASS' if code==0 else 'BLOCKED' if code==2 else 'FAIL',returncode=code,log=log.name,log_sha256=sha256(log));save();return code
    save();print('Results:',out,flush=True)
    if not shutil.which('rustc') or not shutil.which('cargo'):
        report.update(status='BLOCKED',complete=True,reason='rustc/cargo not found; no runtime generated',m1='BLOCKED',m2='BLOCKED');save();return 2
    try:
        # M2 cannot run against untested M1 native foundation.
        build_args=[sys.executable,'tools/build.py','--native','--test']
        tasks=[('build',build_args),('native_runtime',[sys.executable,'tools/validate_runtime.py','--modes','cpu','--capture','--output',out/'native-runtime']),('native_fidelity',[sys.executable,'tools/validate_native_fidelity.py','--capture','--output',out/'native-fidelity'])]
        if a.milestone in ('M1','all'):
            tasks += [('native_cloud',[sys.executable,'tools/capture_native_cloud.py','--output',out/'native-cloud'])]
            if not a.native_only:tasks += [('wasm_build',[sys.executable,'tools/build.py','--web']),('wasm_fidelity',[sys.executable,'tools/validate_wasm_fidelity.py','--output',out/'wasm-fidelity'])]
        for name,cmd in tasks:
            rc=run(name,cmd)
            if rc:report.update(status='BLOCKED' if rc==2 else 'FAIL',complete=True,m1='NOT_PASSED',m2='NOT_RUN');save();return rc
        report['m1']='NATIVE_PASS' if a.native_only or a.milestone=='M2' else 'REPRESENTATIVE_CPU_WASM_PASS';save()
        if a.milestone in ('M2','all'):
            rc=run('m2_rust_ab',['cargo','run','--release','--offline','--manifest-path',cpu_workspace(),'--target-dir',ROOT/'target/cpu','-p','vapor-core','--example','m2_density','--',out/'m2-rust',a.quality])
            report['m2']='DENSITY_AB_EXECUTION_PASS' if not rc else 'NOT_PASSED';save()
            if rc:report.update(status='BLOCKED' if rc==2 else 'FAIL',complete=True);save();return rc
            rc=run('m2_resolved_probe',[sys.executable,'tools/validate_resolved_plume.py','--effects','cigarette_smoke','--models','matched','--seconds','0.25','--timeout','1200','--output',out/'m2-resolved'])
            report['m2']='SHORT_EXECUTION_PROBE_PASS_FULL_TIMELINE_AND_VISUAL_REVIEW_REQUIRED' if not rc else 'NOT_PASSED';save()
            if rc:report.update(status='BLOCKED' if rc==2 else 'FAIL',complete=True);save();return rc
        else:report['m2']='NOT_RUN'
        report.update(status='PASS_EXECUTION_ONLY',complete=True);save();return 0
    except Exception as exc:report.update(status='FAIL',complete=True,reason=str(exc));save();return 1
if __name__=='__main__':raise SystemExit(main())
