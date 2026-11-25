"""Compare actual recorded fields without editing individual render pixels."""
import json,sys
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
p=Path(sys.argv[1]);report=json.loads((p/'experiment.json').read_text());renders=p/'renders'
if report['status']!='PASS_EXECUTION_ONLY':raise ValueError('experiment incomplete')
rows=report['rows'];key=rows[0]['key'];smoke=key=='cigarette_smoke';w,h=(260,340) if smoke else (340,250)
models=['legacy_source','matched','seeded'];assert [r['model'] for r in rows]==models
font=ImageFont.truetype('DejaVuSans.ttf',20);small=ImageFont.truetype('DejaVuSans.ttf',13)
gap=8;left=64;top=84;frames=len(rows[0]['snapshots']);im=Image.new('RGB',(left+3*(w+gap)+8,top+frames*(h+gap)+30),(17,20,26));d=ImageDraw.Draw(im)
d.text((16,12),('Sidestream smoke' if smoke else 'Exhaled aerosol')+' | Resolved near-field CPU experiment',font=font,fill=(235,235,239))
d.text((16,42),f'{rows[0]["cells"]} cells • same material and camera • local cropped domain • not Rust',font=small,fill=(157,171,186))
for j,(row,title) in enumerate(zip(rows,['Legacy momentum + heat','Physical momentum + heat','Physical + 5% source seed'])):
    x=left+j*(w+gap);d.text((x,65),title,font=small,fill=(224,227,232))
    for i,frame in enumerate(row['snapshots']):
        y=top+i*(h+gap);im.paste(Image.open(renders/(frame['stem']+'.png')).convert('RGB'),(x,y))
        if j==0:d.text((12,y+h//2),f'{frame["time"]:.2f}s',font=small,fill=(210,213,220))
d.text((16,im.height-22),'Independent SciPy/Numba MAC/DST and JS optics • experimental shape, not a validated game runtime',font=small,fill=(157,171,186));im.save(p/(key+'-timeline.png'))
