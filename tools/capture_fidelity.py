"""Render real native coarse Float32 fields with the opt-in fidelity renderer."""
import json,hashlib,subprocess,tempfile
from pathlib import Path
from runtime_common import ROOT,sha256
from png_codec import write_rgba

def capture_fidelity(density,temperature,*,effect,cells,extent,density_cap,material,path:Path):
    import numpy as np
    d=np.asarray(density,dtype='<f4').tobytes(order='C');t=np.asarray(temperature,dtype='<f4').tobytes(order='C')
    spec=dict(effect=effect,cells=list(cells),extent=list(extent),densityCap=density_cap,material=material)
    with tempfile.TemporaryDirectory(prefix='vapor-fidelity-') as tmp:
        p=Path(tmp);(p/'spec.json').write_text(json.dumps(spec));(p/'density.f32').write_bytes(d);(p/'temperature.f32').write_bytes(t)
        r=subprocess.run(['node',str(ROOT/'tools/fidelity_field_preview.mjs'),str(p/'spec.json'),str(p/'density.f32'),str(p/'temperature.f32'),str(p/'pixels.rgba')],cwd=ROOT,capture_output=True,text=True,timeout=240)
        if r.returncode:raise RuntimeError('Fidelity preview failed: '+r.stderr[-4000:])
        report=json.loads(r.stdout);pixels=(p/'pixels.rgba').read_bytes()
        if any(report[k]!=hashlib.sha256(v).hexdigest() for k,v in [('densitySha256',d),('temperatureSha256',t),('rgbaSha256',pixels)]):raise RuntimeError('Fidelity input/output hash mismatch')
        write_rgba(path,report['width'],report['height'],pixels);report['file']=path.name;report['sha256']=sha256(path);return report
