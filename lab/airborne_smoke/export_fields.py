"""Export selected artistic VFX frames using the shared lossless VPF1 contract."""
import argparse, hashlib, json, sys
from pathlib import Path
from array import array
import numpy as np
from bake import frame
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'bindings/python'))
from vapor_game.field_asset import BakedField, encode_field_asset, decode_field_asset

def export(output):
    output.mkdir(parents=True,exist_ok=True)
    scene=json.loads((ROOT/'contracts/airborne-smoke.json').read_text())
    rows=[]
    for f in scene['frames']:
        rho,heat=frame(f['frame'])
        assert tuple(rho.shape[::-1])==tuple(scene['cells'])
        fields=[array('f',x.ravel()) for x in (rho,heat)]
        b=encode_field_asset(BakedField(tuple(scene['cells']),tuple(scene['extent']),scene['densityCap'],f['time'],*fields))
        restored=decode_field_asset(b)
        assert restored.density==fields[0] and restored.temperature==fields[1]
        (output/f['file']).write_bytes(b)
        rows.append({**f,'sha256':hashlib.sha256(b).hexdigest(),'density_nonzero':int(np.count_nonzero(rho)), 'density_peak':float(rho.max())})
    result={'scope':'Python procedural artistic fields, exact Python VPF roundtrip; not Rust physics', 'frames':rows}
    (output/'manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=ROOT/'reports/local/lab/airborne-smoke/fields-vpf');export(p.parse_args().output)
