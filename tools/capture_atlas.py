"""Render full-resolution supplied density atlas using the existing JS CPU preview.
Only temporary raw files are written. Actual source/provenance comes from the caller.
"""
import hashlib,json,subprocess,tempfile
from pathlib import Path
from runtime_common import ROOT
from png_codec import write_rgba

def capture_atlas(atlas:bytes,*,cells,extent,density_cap,material,path:Path,background='dark'):
    spec=dict(cells=list(cells),extent=list(extent),densityCap=density_cap,material=material,background=background)
    with tempfile.TemporaryDirectory(prefix='vapor-atlas-preview-') as tmp:
        t=Path(tmp);(t/'spec.json').write_text(json.dumps(spec));(t/'atlas.rgba').write_bytes(atlas)
        p=subprocess.run(['node',str(ROOT/'tools/atlas_preview.mjs'),str(t/'spec.json'),str(t/'atlas.rgba'),str(t/'pixels.rgba')],cwd=ROOT,capture_output=True,text=True,timeout=180)
        if p.returncode:raise RuntimeError('Atlas preview failed: '+p.stderr[-4000:])
        report=json.loads(p.stdout)
        if report['atlasSha256']!=hashlib.sha256(atlas).hexdigest():raise RuntimeError('atlas hash mismatch')
        write_rgba(path,report['width'],report['height'],(t/'pixels.rgba').read_bytes())
        report['file']=path.name;report['sha256']=hashlib.sha256(path.read_bytes()).hexdigest();return report
