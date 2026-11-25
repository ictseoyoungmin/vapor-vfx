"""Compose the actual cache-audit frames; run audit_fidelity_cache.mjs first."""
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
import hashlib,json
import bootstrap  # enables explicit shared validation helpers
from runtime_common import ROOT
p=ROOT/'reports/local/lab/fidelity-cache';j=json.loads((p/'cache-audit.json').read_text())
def font(n):
    for name in ('DejaVuSans.ttf','arial.ttf'):
        try:return ImageFont.truetype(name,n)
        except OSError:pass
    return ImageFont.load_default()
f,ft=font(16),font(19)
width=3*372+24;height=48+sum(max(r['frames'][0]['height'],216)+52 for r in j['rows'])+20
im=Image.new('RGB',(width,height),(18,22,30));d=ImageDraw.Draw(im);d.text((12,12),'Optical-depth cache resolution | actual CPU reference renders',font=ft,fill='#e4e9f4');y=48
for r in j['rows']:
    d.text((12,y),r['key'].replace('_',' ').title(),font=ft,fill='#e4e9f4');y+=25
    for i,v in enumerate(r['frames']):
        x=12+i*372;raw=(p/v['file']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=v['rgbaSha256']:raise RuntimeError('frame hash mismatch')
        frame=Image.frombytes('RGBA',(v['width'],v['height']),raw);im.paste(frame,(x+(360-v['width'])//2,y),frame)
        d.text((x+5,y+v['height']+4),f"{int(v['scale']*100)}% | RGB RMSE {v['rgbRmse255']:.2f}/255",font=f,fill='#b8c4d7')
    y+=r['frames'][0]['height']+27
im.save(p/'cache-comparison.png')
print(p/'cache-comparison.png')
