"""Fictional artistic smoke; unitless scene, not a physical explosion model."""
import numpy as np
from scipy.ndimage import map_coordinates
from pathlib import Path
import json,sys
import os
W=Path(os.environ.get("VAPOR_AIRBORNE_OUTPUT", Path(__file__).resolve().parents[2]/"reports/local/lab/airborne-smoke")).resolve()
cells=(160,112,104); extent=(14.,10.1,9.4); origin=np.array([7.55,3.3,4.7]); fps=16; duration=7.5; event=1.75
rng=np.random.default_rng(832791);tiles=[rng.uniform(-1,1,(32,32,32)).astype(np.float32) for _ in range(6)]
axes=[(np.arange(n,dtype=np.float32)+.5)*e/n for n,e in zip(cells,extent)]
def smooth(a,b,x):
 q=np.clip((x-a)/(b-a),0,1);return q*q*(3-2*q)
def noise(x,y,z,f,j):
 x,y,z=np.broadcast_arrays(x,y,z);return map_coordinates(tiles[j%6],np.array([z*f,y*f,x*f],dtype=np.float32),order=1,mode='grid-wrap',prefilter=False)
P=[]
for i in range(28):
 d=rng.normal(size=3);d/=np.linalg.norm(d);d[1]*=.64;d[1]+=.15
 large=i<9;thin=i>=22
 if thin:d[1]=.40+abs(d[1])*.65
 P.append(dict(d=d,r=rng.uniform(.50,.81) if large else rng.uniform(.19,.39),lag=rng.uniform(0,.16) if large else rng.uniform(.6,1.25) if thin else rng.uniform(.07,.42),phi=rng.uniform(0,6.28),stretch=rng.uniform(.75,1.25,3)*([1,1.6,.9] if thin else [1,1,1]),reach=rng.uniform(.75,1.25) if large else rng.uniform(1.05,1.55),amp=rng.uniform(.82,1.05) if large else rng.uniform(.12,.26) if thin else rng.uniform(.26,.50),seed=rng.uniform(-14,14,3),twist=rng.uniform(-1.1,1.1),large=large))
def frame(i):
 age=i/fps-event;rho=np.zeros(cells[::-1],np.float32);heat=np.zeros_like(rho)
 if age<=0:return rho,heat
 for p in P:
  a=age-p['lag']
  if a<=0:continue
  grow=1-np.exp(-a*3.4);d=p['d'];phi=p['phi'];rise=.29*age+.012*age*age
  center=origin+d*p['reach']*(.12+1.22*grow+.25*a+.13*max(a-.9,0)**1.25)
  center[0]-=.36*age+.22*a*max(d[1],0)+.13*a*np.cos(phi);center[1]+=rise+.42*a*d[1]+.10*a*np.sin(phi);center[2]+=.12*age
  center+=np.array([.22*np.sin(phi+a*.95),.13*np.cos(phi+a*1.2),.18*np.sin(phi+a*.67)])*grow
  radius=p['r']*(.16+1.03*grow+.09*a)*p['stretch']*np.array([1+.065*a,1+.105*a,1+.035*a]);reach=radius*1.85
  slices=[];coords=[]
  for ax,c,e in zip(axes,center,reach):
   l=int(np.searchsorted(ax,c-e));h=int(np.searchsorted(ax,c+e,'right'));slices.append(slice(l,h));coords.append(ax[l:h])
  if min(map(len,coords))==0:continue
  zz,yy,xx=np.meshgrid(coords[2],coords[1],coords[0],indexing='ij',sparse=True)
  X=(xx-center[0])/radius[0];Y=(yy-center[1])/radius[1];Z=(zz-center[2])/radius[2];angle=p['twist']*(.4+.6*grow)*Y+phi+.21*a
  U=np.cos(angle)*X+np.sin(angle)*Z;V=Y;Q=-np.sin(angle)*X+np.cos(angle)*Z;sx,sy,sz=p['seed'];u=U+sx;v=V+sy;q=Q+sz
  U=U+.24*noise(u,v,q,1.35,0);V=V+.20*noise(u+.3,v,q,1.55,1);Q=Q+.24*noise(u,v,q+.8,1.45,2)
  rad=np.sqrt(U*U+V*V+Q*Q);n1=noise(U+sx,V+sy,Q+sz,2.55,3);n2=noise(U+sx,V+sy,Q+sz,5.4,4);n3=noise(U+sx,V+sy,Q+sz,11.5,5)
  edge=1-rad+.40*n1+.17*n2+.075*n3;outer=smooth(-.16,.045,edge);inner=smooth(-.035,.28,edge)
  strength=p['amp']*smooth(0,.09,a)*np.exp(-a*(.24 if p['large'] else .34))*(1-smooth(3.7+.42*np.sin(phi),5.72,age))
  density=outer*(.18+.82*inner)*(.65+.35*n1)*strength;warmth=outer*(.75+.25*n2)*(7.5*np.exp(-age*4.9))*smooth(0,.065,a)
  sl=tuple(slices[::-1]);rho[sl]+=density.astype(np.float32);heat[sl]=np.maximum(heat[sl],warmth.astype(np.float32))
 rho=1-np.exp(-rho*1.65)
 z,y,x=np.meshgrid(axes[2],axes[1],axes[0],indexing='ij',sparse=True);fade=smooth(.05,.5,x)*smooth(.05,.5,y)*smooth(.05,.5,z)*smooth(.05,.5,extent[0]-x)*smooth(.05,.5,extent[1]-y)*smooth(.05,.5,extent[2]-z)
 return np.ascontiguousarray(rho*fade,dtype='<f4'),np.ascontiguousarray(heat*fade,dtype='<f4')
if __name__=='__main__':
 W.mkdir(parents=True,exist_ok=True);(W/'fields').mkdir(exist_ok=True)
 indices=list(map(int,sys.argv[1:])) if len(sys.argv)>1 else list(range(round(event*fps)+1,round(duration*fps)+1))
 cfg=dict(scope='Art-directed fictional smoke; no blast physics',cells=cells,extent=extent,origin=origin.tolist(),fps=fps,duration=duration,event=event,width=960,height=540)
 (W/'config.json').write_text(json.dumps(cfg,indent=2))
 for i in indices:
  stem=f'{i:04d}';rho,heat=frame(i);assert np.isfinite(rho).all() and np.isfinite(heat).all()
  (W/'fields'/f'{stem}.rho').write_bytes(rho.tobytes());(W/'fields'/f'{stem}.heat').write_bytes(heat.tobytes());print(i,float(rho.max()),int(np.count_nonzero(rho>.001)),flush=True)
