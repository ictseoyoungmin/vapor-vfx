#!/usr/bin/env python3
"""Optional Pillow layout of actual benchmark PNGs, enlarged and labeled only."""
from pathlib import Path
import json,hashlib
from PIL import Image,ImageDraw,ImageFont
import bootstrap  # enables explicit shared validation helpers
from runtime_common import ROOT,sha256

def main():
    root=ROOT/'reports/local/lab/effects';path=root/'reprojection-0.10.json';report=json.loads(path.read_text())
    width=1440;margin=32;panelw=452;panelh=282;gap=10;top=104;rowh=342
    rows=report['rows'];im=Image.new('RGB',(width,top+rowh*len(rows)+28),(17,24,35));d=ImageDraw.Draw(im)
    def font(size,bold=False):
        try:return ImageFont.truetype('DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf',size)
        except OSError:return ImageFont.load_default(size=size)
    f=font(20);small=font(17);title=font(29,True);label=font(19,True)
    d.text((margin,22),'Vapor 0.10  /  CPU reference reprojection',font=title,fill=(239,244,251))
    d.text((margin,59),'Final frame of 8-frame orbit + rigid translation; 240 × 150 source images',font=f,fill=(160,174,191))
    names={'cumulus_cloud':'Cumulus cloud','ground_fog':'Ground fog','dust':'Dust'}
    for i,row in enumerate(rows):
        source=root/row['file']
        if sha256(source)!=row['pngSha256']:raise RuntimeError('benchmark PNG hash mismatch')
        y=top+i*rowh;src=Image.open(source).convert('RGB');n=row['width']//3
        d.text((margin,y),names[row['key']],font=label,fill=(239,244,251))
        gain=100*(1-row['meanTemporalMse']/row['meanRawMse'])
        d.text((width-margin,y),f'Average MSE reduction: {gain:.1f}%',font=small,fill=(180,211,205),anchor='ra')
        for j,lab in enumerate(['12 steps / current frame','12 steps / reprojected','192 steps / reference']):
            x=margin+j*(panelw+gap);d.text((x,y+30),lab,font=small,fill=(180,191,205))
            frame=src.crop((j*n,0,(j+1)*n,row['height'])).resize((panelw,panelh),Image.Resampling.BICUBIC);im.paste(frame,(x,y+53))
    output=root/'reprojection-comparison.png';im.save(output)
    report['contactSheet']={'file':output.name,'sha256':sha256(output),'notice':'Labeled layout of three actual final-frame comparisons, enlarged for readability; no added simulated effect.'}
    path.write_text(json.dumps(report,indent=2)+'\n');print(output)
if __name__=='__main__':main()
