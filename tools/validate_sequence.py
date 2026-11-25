#!/usr/bin/env python3
"""Actual large-sequence JS/Python parity, optional real Rust sample+render."""
import argparse,hashlib,json,subprocess,sys,tempfile
from pathlib import Path
from runtime_common import ROOT,default_library,require_receipt,source_fingerprint
from check_sdk import atomic_report
from png_codec import write_rgba
from validate_cloud_equivalence import native_options
sys.path.insert(0,str(ROOT/'bindings/python'))
from vapor_game.field_sequence import FieldSequence
from vapor_game.field_asset import encode_field_asset
from vapor_game.fidelity import FidelityCPU

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('index',type=Path);p.add_argument('--native',action='store_true');p.add_argument('--build',action='store_true');p.add_argument('--output',type=Path,default=ROOT/'reports/local/sequence-parity');a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True);
 for stale in ['rust-sample.vpf','rust.png','native.log','build.log']:
  (out/stale).unlink(missing_ok=True)
 r={'status':'RUNNING','complete':False,'scope':'actual JS/Python fields; native only when explicitly requested','native_status':'NOT_RUN','source_fingerprint':source_fingerprint()};rp=out/'validation.json';atomic_report(rp,r)
 try:
  path=a.index.resolve();s=FieldSequence.open(path);times=s.index.times;rows=[]
  for i,t in enumerate(times):
   for q in ([t,(t+times[i+1])/2] if i+1<len(times) else [t]):rows.append({'time':q,'sha256':hashlib.sha256(encode_field_asset(s.sample(q))).hexdigest()})
  with tempfile.TemporaryDirectory() as tmp:
   dest=Path(tmp)/'js.json';subprocess.run(['node',str(ROOT/'tools/sequence_hashes.mjs'),str(path),str(dest)],check=True,timeout=300);js=json.loads(dest.read_text())
  if js['rows']!=rows:raise RuntimeError('JS/Python sequence mismatch')
  r.update(data_status='PASS',samples=len(rows),voxels_per_field=len(s.sample(times[0]).density),rows=rows,max_cached_frames=2)
  if a.native or a.build:
   atomic_report(rp,r)
   if a.build:
    with (out/'build.log').open('w') as log:rc=subprocess.run([sys.executable,str(ROOT/'tools/build.py'),'--native','--test'],stdout=log,stderr=subprocess.STDOUT,cwd=ROOT,timeout=1800).returncode
    if rc==2:raise FileNotFoundError('actual Rust toolchain unavailable')
    if rc:raise RuntimeError('Rust build/test failed')
   r['receipt']=require_receipt(default_library());mid=(len(times)-1)//2;t=(times[mid]+times[mid+1])*.5 if len(times)>1 else times[0];expected=encode_field_asset(s.sample(t));native=out/'rust-sample.vpf'
   from build import cpu_workspace
   manifest=cpu_workspace();cmd=['cargo','run','--offline','--release','--manifest-path',str(manifest),'--target-dir',str(ROOT/'target/cpu'),'-p','vapor-core','--example','sequence_probe','--',str(path),str(t),str(native)]
   with (out/'native.log').open('w') as log:subprocess.run(cmd,check=True,timeout=1800,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
   if native.read_bytes()!=expected:raise RuntimeError('Rust decoded/interpolated field mismatch')
   scene=json.loads((ROOT/'contracts/cloud-hero.json').read_text());options=native_options(scene,scene['profiles']['preview']);options['lighting']['light_scale']=.5;options['steps']=112
   pixels,_=FidelityCPU(default_library()).render(s.sample(t).native_fields(),**options);write_rgba(out/'rust.png',options['width'],options['height'],pixels);r.update(native_status='PASS_SAMPLE_AND_RENDER_EXECUTION',native_time=t,native_render_sha256=hashlib.sha256(pixels).hexdigest(),notice='Rust playback field exact; render execution only, not compared against JS image')
  r.update(status='PASS',complete=True);code=0
 except FileNotFoundError as e:r.update(status='BLOCKED',native_status='BLOCKED',reason=str(e),complete=True);code=2
 except Exception as e:r.update(status='FAIL',reason=str(e),complete=True);code=1
 atomic_report(rp,r);print(r['status'],rp);return code
if __name__=='__main__':raise SystemExit(main())
