"""Compose actual recorded CPU research frames, without modifying their pixels."""
from pathlib import Path
import sys,json
from PIL import Image, ImageDraw, ImageFont
p=Path(sys.argv[1]);renders=p/'renders';report=json.loads((p/'experiment.json').read_text())
if report['status']!='PASS':raise ValueError('experiment incomplete')
rows={(r['key'],r['model']):r for r in report['rows']}
try:f=ImageFont.truetype('DejaVuSans.ttf',18);small=ImageFont.truetype('DejaVuSans.ttf',12)
except OSError:f=small=ImageFont.load_default()
for effect,sz in [('cigarette_smoke',(240,300)),('exhaled_aerosol',(300,240))]:
    w,h=sz;gap=8;top=72;left=66;im=Image.new('RGB',(left+3*(w+gap),top+3*(h+gap)+26),(17,20,26));d=ImageDraw.Draw(im)
    d.text((14,10),('Sidestream smoke' if effect=='cigarette_smoke' else 'Exhaled aerosol')+' | CPU research',font=f,fill=(235,235,239))
    d.text((14,38),'Same camera and original material • independent SciPy MAC + JS optics • not Rust',font=small,fill=(157,171,186))
    for j,(model,title) in enumerate([('legacy','MacCormack'),('muscl','MUSCL'),('physical','MUSCL + physical source')]):
        x=left+j*(w+gap);d.text((x,57),title,font=small,fill=(224,227,232))
        for i,frame in enumerate(rows[(effect,model)]['snapshots']):
            y=top+i*(h+gap);file=renders/(frame['stem']+'.png');im.paste(Image.open(file).convert('RGB'),(x,y))
            if j==0:d.text((13,y+h//2),f'{frame["time"]:.2f} s',font=small,fill=(210,213,220))
    d.text((14,im.height-19),'Experimental density transport — no claim of visual or Rust/GPU parity',font=small,fill=(157,171,186));im.save(p/(effect+'-timeline.png'))
