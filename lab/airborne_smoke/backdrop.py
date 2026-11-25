import numpy as np
from scipy.ndimage import zoom,gaussian_filter
from pathlib import Path
w,h=960,540; rng=np.random.default_rng(912)
y,x=np.mgrid[0:h,0:w].astype(np.float32); v=y/(h-1);u=x/(w-1)
a=np.power(v,2.25); sun=np.exp(-((u-.10)**2+(v-.10)**2)*8)
base=np.stack([.034+.23*a+.065*sun,.105+.26*a+.04*sun,.285+.23*a+.025*sun],-1)
# High distant streaks are deliberately low contrast, separate from the foreground VFX.
def texture(gy,gx):
 n=rng.random((gy,gx));return zoom(n,(h/gy,w/gx),order=3)[:h,:w]
cloud=np.clip((texture(32,7)*.65+texture(69,20)*.35-.53)*2.1,0,1)
cloud*=np.exp(-((v-.17)/.16)**2)*.28
base=base*(1-cloud[...,None])+np.array([.53,.59,.63])*cloud[...,None]
# Distant atmospheric ridge layers low in the frame; no foreground clutter.
for k,(height,rough,col) in enumerate([(0.91,.065,[.16,.24,.30]),(.947,.055,[.088,.152,.192]),(.978,.045,[.045,.094,.13])]):
 ridge=np.zeros(w)
 for o in range(6):
  a=rng.uniform(-1,1,8*2**o);ridge+=np.interp(np.arange(w)/(w-1),np.linspace(0,1,len(a)),a)*.49**o
 ridge=gaussian_filter(ridge,.9)
 ridge=height+rough*.62*ridge
 mask=np.clip((v-ridge[None,:])*h+.5,0,1);c=np.asarray(col)[None,None,:]*(.90+.10*np.sin(u*14+k))[...,None];base=base*(1-mask[...,None])+c*mask[...,None]
import os
W=Path(os.environ.get("VAPOR_AIRBORNE_OUTPUT", Path(__file__).resolve().parents[2]/"reports/local/lab/airborne-smoke")).resolve()
W.mkdir(parents=True,exist_ok=True)
(W/'background.f32').write_bytes(np.ascontiguousarray(base,dtype='<f4').tobytes())
