"""Layout actual raw frames from render_scene_depth.mjs. No effect is added."""
import json,hashlib
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
import bootstrap  # enables explicit shared validation helpers
from runtime_common import ROOT,sha256
p=ROOT/'reports/local/lab/effects';rp=p/'scene-depth-0.12.json';r=json.loads(rp.read_text());w,h=r['width'],r['height'];frames=[]
for i,hash_ in enumerate(r['rawFrameHashes']):
    raw=p/f'scene-depth-{i}.rgba';data=raw.read_bytes()
    if hashlib.sha256(data).hexdigest()!=hash_:raise ValueError('frame hash mismatch')
    im=Image.frombytes('RGBA',(w,h),data).convert('RGB');im.save(p/f'scene-depth-{i}.png');frames.append(im);raw.unlink()
font=lambda n,b=False:ImageFont.truetype('DejaVuSans-Bold.ttf' if b else 'DejaVuSans.ttf',n)
m=24;gap=12;out=Image.new('RGB',(3*w+2*gap+2*m,h+142),(16,24,34));d=ImageDraw.Draw(out);d.text((m,18),'Vapor 0.12  /  Scene-aware ground fog',font=font(29,True),fill='#f4f7fb');d.text((m,58),'Actual CPU procedural volume and analytic opaque geometry · fixed camera · same density field',font=font(20),fill='#a7bacb')
for i,(im,label) in enumerate(zip(frames,['01  Opaque scene','02  Without depth clipping','03  With depth clipping'])):
    x=m+i*(w+gap);d.text((x,99),label,font=font(20,True),fill='#e4eef8');out.paste(im,(x,130))
output=p/'scene-depth-comparison.png';out.save(output);r['imageFiles']=[{'file':f.name,'sha256':sha256(f)} for f in [p/f'scene-depth-{i}.png' for i in range(3)]+[output]];rp.write_text(json.dumps(r,indent=2)+'\n');print(output)
