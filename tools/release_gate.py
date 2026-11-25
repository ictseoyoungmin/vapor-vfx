#!/usr/bin/env python3
"""M1–M5 representative host release assessment. Never closes unfinished milestones.
Actual Rust required; representative WebGPU path instead of every game editor.
Cloud parity is kept independent from unresolved physical smoke fidelity.
"""
import argparse,json,shutil,subprocess,sys,tempfile
from pathlib import Path
from runtime_common import ROOT,source_fingerprint,sha256
from check_sdk import atomic_report

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--channel',choices=['msedge','chrome']);p.add_argument('--native-only',action='store_true',help='skip WASM/WebGPU; cannot close M1/M4/M5');p.add_argument('--full-plume',action='store_true',help='run all six actual local Rust 4s scenarios, not just short probe');p.add_argument('--skip-gpu',action='store_true');p.add_argument('--output',type=Path,default=ROOT/'reports/local/release');a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True);out=Path(tempfile.mkdtemp(prefix='run-',dir=a.output.resolve()));rp=out/'gate.json';report=dict(schema='vapor.release-assessment/1',status='RUNNING',complete=False,source_fingerprint=source_fingerprint(),production_release_ready=False,milestones={},steps=[])
    def save():atomic_report(rp,report)
    def milestone(key,status,reason,**kw):report['milestones'][key]=dict(status=status,reason=reason,**kw);save()
    def run(name,cmd,timeout=3600):
        log=out/(name+'.log');cmd=list(map(str,cmd));row=dict(name=name,command=cmd,status='RUNNING');report['steps'].append(row);save()
        with log.open('w') as f:
            try:rc=subprocess.run(cmd,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,timeout=timeout).returncode
            except (OSError,subprocess.TimeoutExpired) as e:f.write(str(e));rc=1
        row.update(status='PASS' if rc==0 else 'BLOCKED' if rc==2 else 'FAIL',returncode=rc,log=log.name,log_sha256=sha256(log));save();return rc
    py=sys.executable;print(out,flush=True);save()
    try:
        # Generate high-quality reference even when the toolchain is absent. No Rust fallback.
        cloud=out/'cloud';cloud_rc=run('canonical_cloud',[py,'tools/validate_cloud_equivalence.py','--profile','hero','--build','--output',cloud])
        if cloud_rc:
            milestone('M1','BLOCKED' if cloud_rc==2 else 'FAIL','Full cloud equivalence did not pass; see canonical_cloud.log')
        else:
            cpu=run('native_runtime',[py,'tools/validate_runtime.py','--modes','cpu','--capture','--output',out/'native-runtime'])
            nf=run('native_fidelity',[py,'tools/validate_native_fidelity.py','--capture','--output',out/'native-fidelity'])
            wb=wf=None
            if not a.native_only:
                wb=run('wasm_build',[py,'tools/build.py','--web']);wf=run('wasm_fidelity',[py,'tools/validate_wasm_fidelity.py','--output',out/'wasm-fidelity']) if wb==0 else wb
            passed=cpu==nf==0 and wb==wf==0
            milestone('M1','PASS' if passed else 'PARTIAL' if cpu==nf==0 and a.native_only else 'FAIL','Representative native + WASM runtime, full cloud and small fidelity parity' if passed else 'Some required runtime gates incomplete')
            if passed:
                package_path=ROOT.parent/f'vapor-evaluation-{out.name}.zip'
                # Stage verified candidate BEFORE any optional GPU build replaces native artifact.
                package_rc=run('evaluation_package',[py,'tools/package_runtime_candidate.py',package_path,'--native-evidence',out/'native-fidelity/validation.json','--wasm-evidence',out/'wasm-fidelity/validation.json','--cloud-evidence',cloud/'validation.json'])
                report['evaluation_package']=str(package_path) if package_rc==0 else None;save()
        m1=report['milestones']['M1']['status']
        if m1 in ('PASS','PARTIAL'):
            args=[py,'tools/validate_resolved_plume.py','--output',out/'m2']+(['--seconds','4'] if a.full_plume else ['--effects','cigarette_smoke','--models','matched','--seconds','0.25'])
            rc=run('m2_local_rust',args,timeout=24000);milestone('M2','IN_PROGRESS' if rc==0 else 'BLOCKED' if rc==2 else 'FAIL','Local execution cannot certify coupled near/far pressure/momentum, obstacle support or full-plume appearance',local_probe_returncode=rc)
        else:milestone('M2','BLOCKED','Rust foundation incomplete; scalar interface research is independent, not M2 completion')
        if m1=='PASS' and not a.skip_gpu:
            args=[py,'tools/validate_cloud_webgpu.py','--output',out/'cloud-webgpu']+(['--channel',a.channel] if a.channel else []);cg=run('m3_m4_cloud_webgpu',args)
            gr=run('gpu_hybrid_runtime',[py,'tools/validate_runtime.py','--build','--modes','gpu','hybrid','--capture','--output',out/'gpu-hybrid'])
            milestone('M3','IN_PROGRESS' if cg==gr==0 else 'BLOCKED' if 2 in (cg,gr) else 'FAIL','Cloud optics and existing GPU/Hybrid runtime checked; effect-specific droplet physics and full fluid optics not accepted',cloud_gpu_returncode=cg,gpu_hybrid_returncode=gr)
            milestone('M4','IN_PROGRESS' if cg==0 else 'BLOCKED' if cg==2 else 'FAIL','Representative cloud render/caching/depth/update timing only; representative whole game workload and other runtime integration not accepted',cloud_gpu_returncode=cg)
        else:
            milestone('M3','BLOCKED' if m1!='PASS' else 'NOT_RUN','GPU fidelity validation requires actual WASM and device')
            milestone('M4','BLOCKED' if m1!='PASS' else 'NOT_RUN','Representative WebGPU integration and performance not measured')
        milestone('M5','NOT_READY','Runtime evaluation package, if created, is not a release. M2–M4 acceptance and rights/redistribution review remain open.')
        report.update(status='BLOCKED' if m1=='BLOCKED' else 'INCOMPLETE',complete=True);save();return 2 if m1=='BLOCKED' else 1
    except Exception as e:report.update(status='FAIL',complete=True,reason=str(e));save();return 1
if __name__=='__main__':raise SystemExit(main())
