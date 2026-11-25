#!/usr/bin/env python3
"""Only accept a receipt-bound actual Rust WASM build; compare full golden fields."""
import argparse,subprocess,sys,json
from pathlib import Path
from runtime_common import ROOT,require_receipt
from check_sdk import atomic_report

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=ROOT/'reports/local/wasm-fidelity');a=p.parse_args()
    path=a.output/'validation.json';artifact=ROOT/'bindings/web/vapor.wasm'
    report={'complete':False,'status':'RUNNING','evidence':'Actual Rust WASM; no JS reference fallback'}
    atomic_report(path,report)
    try:
        receipt=require_receipt(artifact)
        if 'wasm' not in receipt.get('features',[]):raise RuntimeError('WASM build receipt required')
        report['receipt']=receipt
        p=subprocess.run(['node',str(ROOT/'tools/validate_wasm_fidelity.mjs'),str(artifact)],cwd=ROOT,capture_output=True,text=True,timeout=500)
        if p.returncode:raise RuntimeError(p.stdout+'\n'+p.stderr)
        report['rows']=json.loads(p.stdout);report.update(status='PASS',complete=True);code=0
    except FileNotFoundError as e:report.update(status='BLOCKED',complete=True,reason=str(e));code=2
    except Exception as e:report.update(status='FAIL',complete=True,reason=str(e));code=1
    atomic_report(path,report);print(report['status'],path);return code
if __name__=='__main__':raise SystemExit(main())
