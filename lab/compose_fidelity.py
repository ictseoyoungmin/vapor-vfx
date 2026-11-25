"""Compose labelled sheets from verified actual RGBA captures; no density or image synthesis."""
from pathlib import Path
import json,hashlib
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'reports/local/lab/fidelity'
font=ImageFont.load_default(size=19) if hasattr(ImageFont,'load_default') else ImageFont.load_default()
small=ImageFont.load_default(size=13)
rows={}
for report in ['render-report.json','fog-comparison.json','plume-comparison.json']:
    for row in json.loads((D/report).read_text())['rows']:
        name=row['name'];data=(D/(name+'.rgba')).read_bytes()
        if hashlib.sha256(data).hexdigest()!=row['rgbaSha256']:raise ValueError(f'capture hash mismatch: {name}')
        im=Image.frombytes('RGBA',(row['width'],row['height']),data).convert('RGB');im.save(D/(name+'.png'));rows[name]=im

def sheet(name,title,items,w):
    ims=[]
    for key,label in items:
        im=rows[key];h=round(im.height*w/im.width);ims.append((im.resize((w,h),Image.Resampling.LANCZOS),label))
    margin=20;gap=14;header=54;bottom=42;hh=max(i.height for i,_ in ims);out=Image.new('RGB',(margin*2+w*len(ims)+gap*(len(ims)-1),header+hh+bottom+margin),'#101924');d=ImageDraw.Draw(out);d.text((margin,15),title,font=font,fill='#f1f5f9')
    for i,(im,label) in enumerate(ims):
        x=margin+i*(w+gap);out.paste(im,(x,header));d.text((x,header+hh+12),label,font=small,fill='#cbd5e1')
    out.save(D/(name+'.png'))
sheet('cloud-comparison','Cumulus | same camera, 144 x 72 x 96 grid, 112 ray steps', [('cloud-legacy','0.12 density + optics'),('cloud-optics','0.12 density + new optics'),('cloud-fidelity','New density + new optics')],480)
sheet('fog-comparison','Terrain fog | actual analytic scene, identical camera', [('fog-valley-clear','Without volume'),('fog-valley','Terrain-relative density + new optics')],640)
for name,title,w in [('cigarette_smoke','Sidestream smoke | independent CPU MAC reference at 2 s',300),('exhaled_aerosol','Exhaled aerosol | independent CPU MAC reference at 2 s',460)]:
    sheet(name+'-comparison',title,[(name+'-compare-baseline','Medium / original forcing'),(name+'-compare-forced','Medium / coherent forcing'),(name+'-compare-high','High / coherent forcing'),(name+'-compare-detail','Medium MAC / 4x scalar')],w)
print('Verified and converted',len(rows),'actual captures; wrote 4 comparison sheets')
