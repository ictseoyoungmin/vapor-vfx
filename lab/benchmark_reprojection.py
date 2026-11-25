#!/usr/bin/env python3
"""Generate actual procedural volume reprojection comparison PNGs and measurements."""
from __future__ import annotations
import json,subprocess,tempfile
from pathlib import Path
import bootstrap  # enables explicit shared validation helpers
from runtime_common import ROOT,sha256
from png_codec import write_rgba

def main():
    out=ROOT/'reports/local/lab/effects';out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='vapor-reprojection-') as tmp:
        subprocess.run(['node',str(ROOT/'lab/benchmark_reprojection.mjs'),tmp],cwd=ROOT,check=True,timeout=240)
        directory=Path(tmp);report=json.loads((directory/'reprojection.json').read_text())
        for row in report['rows']:
            raw=directory/row['file']
            if sha256(raw)!=row['rawImageSha256']:raise RuntimeError('raw image hash mismatch')
            path=out/(row['key']+'-reprojection.png');write_rgba(path,row['width'],row['height'],raw.read_bytes());row['file']=path.name;row['pngSha256']=sha256(path)
            print(row['key'], 'raw MSE',round(row['meanRawMse'],4),'temporal MSE',round(row['meanTemporalMse'],4),'history',round(row['meanHistoryFraction']*100,1),'%')
        (out/'reprojection-0.10.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
