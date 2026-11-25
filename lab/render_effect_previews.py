#!/usr/bin/env python3
"""Execute Node CPU procedural presets + software ray marcher, encode actual pixels."""
import json, subprocess, sys
import bootstrap  # enables explicit shared validation helpers
from runtime_common import ROOT,clear_previous_outputs,sha256
from png_codec import write_rgba

def main():
    out=ROOT/'reports/local/lab/effects';out.mkdir(parents=True,exist_ok=True)
    keys=['cumulus_cloud','ground_fog','dust']
    clear_previous_outputs(out,['preview-node.json']+[k+ext for k in keys for ext in ('.rgba','.png')])
    try:
        subprocess.run(['node','lab/render_effect_previews.mjs'],cwd=ROOT,check=True,timeout=120)
        path=out/'preview-node.json';report=json.loads(path.read_text())
        if [r['key'] for r in report['reports']]!=keys:raise RuntimeError('missing preset capture')
        for row in report['reports']:
            raw=out/(row['key']+'.rgba');png=out/(row['key']+'.png')
            write_rgba(png,row['width'],row['height'],raw.read_bytes());raw.unlink()
            row['image_sha256']=sha256(png);row['image']=png.name
        path.write_text(json.dumps(report,indent=2)+'\n');return 0
    except Exception as error:
        clear_previous_outputs(out,[k+ext for k in keys for ext in ('.rgba','.png')]);(out/'preview-node.json').write_text(json.dumps({'status':'FAIL','error':str(error)},indent=2)+'\n');print(error,file=sys.stderr);return 1
if __name__=='__main__':raise SystemExit(main())
