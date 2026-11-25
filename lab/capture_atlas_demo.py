#!/usr/bin/env python3
"""Exercise the real JS procedural source and the same atlas preview bridge as native validation."""
import json, subprocess, tempfile
from pathlib import Path
import bootstrap  # enables explicit shared validation helpers
from runtime_common import ROOT
from capture_atlas import capture_atlas

def main():
    script = '''import {createEffect} from './bindings/web/effects.mjs';
import {writeFile} from 'node:fs/promises';
import {join} from 'node:path';
const dir=process.argv[1],e=await createEffect('cumulus_cloud',{quality:'medium'});
try{e.play(); e.advance(.25); const atlas=await e.atlasRGBA8();
await writeFile(join(dir,'atlas.rgba'),atlas);
await writeFile(join(dir,'spec.json'),JSON.stringify({cells:[...e.renderCells],extent:e.extent,density_cap:e.config.densityCap,material:e.definition.material}));}finally{e.dispose();}'''
    out=ROOT/'reports/local/lab/effects';out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='vapor-atlas-demo-') as t:
        subprocess.run(['node','--input-type=module','-e',script,t],cwd=ROOT,check=True,timeout=120)
        d=Path(t);spec=json.loads((d/'spec.json').read_text())
        report=capture_atlas((d/'atlas.rgba').read_bytes(),**spec,path=out/'atlas-demo-cumulus.png',background='sky')
        report.update(source='Actual JS procedural CPU cumulus_cloud, medium, time=0.25; not Rust or game renderer',sdk_version='0.12.0',cells=spec['cells'],extent=spec['extent'])
        (out/'atlas-demo-cumulus.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))
if __name__=='__main__':main()
