#!/usr/bin/env python3
"""Generate PNG timeline sheets from actual public JS Effect API output."""
import json,subprocess,tempfile
from pathlib import Path
import bootstrap  # enables explicit shared validation helpers
from runtime_common import ROOT,sha256
from png_codec import write_rgba

def main():
    out=ROOT/'reports/local/lab/effects';out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='vapor-procedural-timeline-') as tmp:
        subprocess.run(['node',str(ROOT/'lab/profile_procedural.mjs'),tmp],cwd=ROOT,check=True,timeout=180)
        d=Path(tmp);r=json.loads((d/'timeline.json').read_text())
        for row in r['rows']:
            raw=d/row['file']
            if sha256(raw)!=row['rawImageSha256']:raise RuntimeError('raw timeline hash mismatch')
            file=out/(row['key']+'-timeline.png');write_rgba(file,row['width'],row['height'],raw.read_bytes());row['file']=file.name;row['pngSha256']=sha256(file)
        (out/'procedural-timeline-0.9.json').write_text(json.dumps(r,indent=2)+'\n')
        print('PASS actual procedural timeline:',', '.join(row['file'] for row in r['rows']))
if __name__=='__main__':main()
