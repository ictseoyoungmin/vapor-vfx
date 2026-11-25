"""Capture actual coarse f32 fields supplied by the profile runner, with source hashes."""
import hashlib,json,subprocess,tempfile
from pathlib import Path
from runtime_common import ROOT,sha256
from png_codec import write_rgba

def capture_float(density,temperature,*,cells,extent,density_cap,material,path:Path):
    import numpy as np
    d=np.asarray(density,dtype='<f4').tobytes(order='C');t=np.asarray(temperature,dtype='<f4').tobytes(order='C')
    spec=dict(cells=list(cells),extent=list(extent),densityCap=density_cap,material=material)
    with tempfile.TemporaryDirectory(prefix='vapor-float-preview-') as tmp:
        p=Path(tmp);(p/'spec.json').write_text(json.dumps(spec));(p/'density.f32').write_bytes(d);(p/'temperature.f32').write_bytes(t)
        r=subprocess.run(['node',str(ROOT/'tools/float_preview.mjs'),str(p/'spec.json'),str(p/'density.f32'),str(p/'temperature.f32'),str(p/'pixels.rgba')],cwd=ROOT,capture_output=True,text=True,timeout=180)
        if r.returncode:raise RuntimeError('Float preview failed: '+r.stderr[-4000:])
        report=json.loads(r.stdout)
        if report['densitySha256']!=hashlib.sha256(d).hexdigest() or report['temperatureSha256']!=hashlib.sha256(t).hexdigest():raise RuntimeError('float field hash mismatch')
        write_rgba(path,report['width'],report['height'],(p/'pixels.rgba').read_bytes());report['file']=path.name;report['sha256']=sha256(path);return report
