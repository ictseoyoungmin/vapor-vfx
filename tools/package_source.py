#!/usr/bin/env python3
"""Deterministic source/full ZIP; optional current example assets, no history or scratch."""
import argparse,hashlib,json,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DIRS={'.github','crates','bindings','adapters','shaders','effects','include','examples','contracts','fixtures','tests','tools','lab','docs','site'}
FILES={'.gitignore','Cargo.toml','Cargo.lock','README.md','CHANGELOG.md','project.json','CONTRIBUTING.md'}
REPORTS={'reports/README.md','reports/validation-current.json','reports/research-transport.json','reports/emitter-kernel-audit.json','reports/runtime-attempts.json','reports/milestone-status.json','reports/research-coupled-density.json','reports/research-pressure.json','reports/research-resolved-plume.json','reports/research-nested-scalar.json','reports/cloud-equivalence.json','reports/release-assessment.json','reports/field-assets.json','reports/research-lagrangian.json','reports/optical-calibration.json','reports/target-assessment.json','reports/cloud-motion.json','reports/full-domain-aerosol.json','reports/sequence-parity.json','reports/airborne-example.json','reports/pages-preview.json'}
EXCLUDED={'__pycache__','.git','.godot','target','dist','build','node_modules','obj','bin','Plugins','Binaries','Intermediate','Win64'}
def allowed(p,include_assets=False):
    r=p.relative_to(ROOT);parts=r.parts
    if any(x in EXCLUDED for x in parts) or p.suffix in ('.pyc','.pyo','.dll','.so','.dylib','.wasm','.lib','.exe','.node'):return False
    if p.name.endswith('.build.json'):return False
    if include_assets and len(parts)>1 and parts[0]=='assets':
        return (len(parts)==2 and p.name=='README.md') or (parts[1] in {'airborne-smoke','cloud-motion','cloud-hero','field-assets'} and p.suffix in {'.vpf','.vpa','.json','.png'})
    return r.as_posix() in REPORTS or (len(parts)==1 and p.name in FILES) or (len(parts)>1 and parts[0] in DIRS)
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('output',type=Path);ap.add_argument('--include-assets',action='store_true');a=ap.parse_args();out=a.output.resolve()
    if out.is_relative_to(ROOT):ap.error('write outside source root')
    version=json.loads((ROOT/'project.json').read_text())['distribution_version'];prefix=f'vapor_{version}/'
    files=sorted(p for p in ROOT.rglob('*') if p.is_file() and not p.is_symlink() and allowed(p,a.include_assets))
    hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    manifest=''.join(f'{v}  {k}\n' for k,v in hashes.items());(ROOT/'MANIFEST.sha256').write_text(manifest)
    def entry(z,name,data):
        info=zipfile.ZipInfo(prefix+name,date_time=(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;z.writestr(info,data,compresslevel=9)
    out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,'w') as z:
        for p in files:entry(z,p.relative_to(ROOT).as_posix(),p.read_bytes())
        entry(z,'MANIFEST.sha256',manifest.encode())
    with zipfile.ZipFile(out) as z:
        assert z.testzip() is None
        assert len(z.namelist())==len(hashes)+1
        for name,sha in hashes.items():assert hashlib.sha256(z.read(prefix+name)).hexdigest()==sha,name
    print(f'PASS package: {len(hashes)+1} files, {out.stat().st_size} bytes')
if __name__=='__main__':main()
