#!/usr/bin/env python3
"""Package a receipt-bound *evaluation* build for the current desktop host + WASM.
Never publishes, signs, licenses or declares the M5 release complete. Requires
actual cloud equivalence PASS plus native and WASM parity from the same source.
"""
from __future__ import annotations
import argparse,json,hashlib,zipfile,platform
from pathlib import Path
from runtime_common import ROOT,default_library,require_receipt,sha256,source_fingerprint,receipt_path
from package_source import allowed

def checked_report(path,receipt,*,cloud=False):
    d=json.loads(path.read_text());
    if d.get('complete') is not True or d.get('status')!='PASS':raise ValueError(f'actual successful runtime report required: {path}')
    r=d.get('receipt',{});
    if r.get('source_fingerprint')!=source_fingerprint() or r.get('artifact_sha256')!=receipt['artifact_sha256']:raise ValueError(f'stale or mismatched evidence: {path}')
    if cloud:
        if d.get('schema')!='vapor.cloud-equivalence/1' or d.get('profile')!='hero' or d.get('reference_status')!='PASS' or d.get('rust_status')!='PASS' or d.get('scene_sha256')!=sha256(ROOT/'contracts/cloud-hero.json'):raise ValueError('full canonical cloud equivalence required')
        keys={'density','temperature','isolated_alpha','isolated_rgba','end_to_end_alpha','end_to_end_rgba'};c=d.get('comparison',{});
        if set(c)!=keys or any(not x.get('passed') or x.get('violations')!=0 for x in c.values()):raise ValueError('cloud field/optics/end-to-end checks must pass')
        for file,key in [('rust.png','rust_png_sha256'),('reference.png','reference_png_sha256')]:
            if sha256(path.parent/file)!=d.get(key):raise ValueError('cloud capture hash mismatch')
    elif not d.get('rows') or len(d['rows'])!=4:raise ValueError('all four fidelity cases required')
    return d

def package(output,native_evidence,wasm_evidence,cloud_evidence):
    native=default_library();wasm=ROOT/'bindings/web/vapor.wasm';nr=require_receipt(native);wr=require_receipt(wasm)
    if 'cpu' not in nr['features'] or 'wasm' not in wr['features']:raise ValueError('native + WASM Rust artifacts required')
    checked_report(native_evidence,nr);checked_report(wasm_evidence,wr);checked_report(cloud_evidence,nr,cloud=True)
    # Evaluation archive includes active source (for C++/.NET builds) plus verified native and WASM artifacts.
    output=output.resolve();
    if output.is_relative_to(ROOT) or output.exists():raise ValueError('choose a new output outside source root')
    files={p.relative_to(ROOT).as_posix():p for p in ROOT.rglob('*') if p.is_file() and not p.is_symlink() and allowed(p)}
    for p in (native,receipt_path(native),wasm,receipt_path(wasm)):files[p.relative_to(ROOT).as_posix()]=p
    if platform.system()=='Windows':
        lib=native.with_name('vapor.dll.lib');
        if lib.is_file():files[lib.relative_to(ROOT).as_posix()]=lib
    for name,p in [('native-fidelity.json',native_evidence),('wasm-fidelity.json',wasm_evidence),('cloud-equivalence.json',cloud_evidence),('cloud-rust.png',cloud_evidence.parent/'rust.png'),('cloud-reference.png',cloud_evidence.parent/'reference.png')]:files['evaluation/'+name]=p
    meta={'schema':'vapor.evaluation-package/1','scope':'current host + WASM, actual CPU fidelity parity only','production_release_ready':False,'host':platform.platform(),'source_fingerprint':source_fingerprint(),'native_sha256':nr['artifact_sha256'],'wasm_sha256':wr['artifact_sha256'],'limitations':['M2 near/far momentum/pressure and fluid visual acceptance pending','GPU/Hybrid correctness and game frame cost separate','license/redistribution rights not established']}
    manifest={name:sha256(p) for name,p in files.items()};meta_bytes=(json.dumps(meta,indent=2)+'\n').encode();manifest['evaluation/package.json']=hashlib.sha256(meta_bytes).hexdigest()
    output.parent.mkdir(parents=True,exist_ok=True)
    try:
        with zipfile.ZipFile(output,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for name,p in sorted(files.items()):z.write(p,'vapor/'+name)
            z.writestr('vapor/evaluation/package.json',meta_bytes);z.writestr('vapor/MANIFEST.sha256',''.join(f'{sha}  {name}\n' for name,sha in sorted(manifest.items())))
        with zipfile.ZipFile(output) as z:
            if z.testzip() or any(hashlib.sha256(z.read('vapor/'+name)).hexdigest()!=sha for name,sha in manifest.items()):raise RuntimeError('evaluation archive integrity failed')
    except BaseException:
        if output.is_file():output.unlink()
        raise
    return output

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);p.add_argument('--native-evidence',type=Path,required=True);p.add_argument('--wasm-evidence',type=Path,required=True);p.add_argument('--cloud-evidence',type=Path,required=True);a=p.parse_args()
    try:print('EVALUATION PACKAGE',package(a.output,a.native_evidence,a.wasm_evidence,a.cloud_evidence));return 0
    except FileNotFoundError as e:print('BLOCKED:',e);return 2
    except Exception as e:print('FAIL:',e);return 1
if __name__=='__main__':raise SystemExit(main())
