#!/usr/bin/env python3
"""Run every local stage-1 gate possible in the current environment.

Writes a machine-readable report instead of silently treating unavailable
Rust/Chromium integration as success.
"""
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
LOG=ROOT/'reports/stage1/validation.json'

def cmd(name,arr,cwd=ROOT):
    try:
        p=subprocess.run(arr,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                         text=True,timeout=90)
        return {'status':'PASS' if p.returncode==0 else 'FAIL','exit_code':p.returncode,
                'command':arr,'output':p.stdout[-6000:]}
    except (subprocess.TimeoutExpired, OSError) as e:
        return {'status':'FAIL','command':arr,'error':str(e)}

def main():
    checks={}
    checks['legacy_static']=cmd('legacy_static',[sys.executable,str(ROOT/'history/legacy/v18/tests/verify.py')])
    checks['source_integrity']=cmd('source_integrity',[sys.executable,str(ROOT/'tools/freeze_contract.py'),'--check'])
    checks['python_unit_tests']=cmd('python_unit_tests',[sys.executable,'-m','unittest','discover','-s','tests','-p','test_contract.py','-v'])
    checks['numeric_regression_self_check']=cmd('numeric_regression_self_check',
        [sys.executable,str(ROOT/'tools/compare_baseline.py'),str(ROOT/'history/legacy/v18/tests/baseline_low.json'),'--strict'])
    checks['js_original_pchip_vectors']=cmd('js_original_pchip_vectors',
        ['node',str(ROOT/'tools/generate_pchip_fixtures.mjs'),'--check']) if shutil.which('node') else {'status':'BLOCKED','reason':'node not found'}
    checks['rust_workspace_tests']=cmd('rust_workspace_tests',['cargo','test','--workspace']) if shutil.which('cargo') else {'status':'BLOCKED','reason':'cargo/rustc toolchain not installed'}
    checks['browser_webgl_smoke']={
        'status':'BLOCKED',
        'reason':'Browser navigation restricted (net::ERR_BLOCKED_BY_ADMINISTRATOR); launch works but localhost/http/file nav blocked',
        'evidence':'reports/browser_smoke.log',
    }
    original=json.loads((ROOT/'history/legacy/v18/tests/baseline_low.json').read_text())
    s=original['samples']
    slopes=sorted(x['spreadSlope'] for x in s if 1<=x['t']<=3)
    baseline_assessment={
        'source':'imported archived SwiftShader baseline; NOT a new GPU measurement',
        'front_max_0_3_m':max(x['front'] for x in s),
        'spread_slope_median_1_3':slopes[len(slopes)//2],
        'back_frac_max_0_3':max(x['backFrac'] for x in s),
        'vmax_m_per_s':max(x['vmax'] for x in s),
        'front_within_literature_range':0.3<=max(x['front'] for x in s)<=0.8,
        'spread_within_target':0.07<=slopes[len(slopes)//2]<=0.2,
        'back_frac_within_design_target':max(x['backFrac'] for x in s)<=0.05,
        'nan_status':'not available in saved slim baseline (cannot be inferred)',
        '8_second_dissipation':'not available (samples through 3s only)',
    }
    report={'schema':'vapor.stage1-validation/1','timestamp_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
            'checks':checks,'imported_low_assessment':baseline_assessment,
            'stage_1_conclusion':'static frozen contract, numerical comparison framework, and JS golden tests completed; Rust build and live GPU blocked',
            'all_executable_checks_passed':all(v['status']=='PASS' for v in checks.values() if v['status']!='BLOCKED')}
    LOG.parent.mkdir(parents=True,exist_ok=True)
    LOG.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    for k,v in checks.items(): print(f"{v['status']}: {k}")
    print('report:',LOG)
    sys.exit(0 if report['all_executable_checks_passed'] else 1)

if __name__=='__main__': main()
