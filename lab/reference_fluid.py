"""Independent NumPy/SciPy MAC plume solver, validation only.
Actual 3D advection and buoyancy, with a spectral (DST) pressure solve instead
of the Rust solver's finite SOR. Open boundaries, one source, no obstacles.
Not a production backend, and NOT evidence of Rust or GPU execution/parity.
"""
from __future__ import annotations
import argparse, hashlib, json, time
from pathlib import Path
import numpy as np
from scipy.ndimage import map_coordinates
from scipy.fft import dstn,idstn
from scipy.interpolate import CubicHermiteSpline
import bootstrap  # enables explicit shared validation helpers
from runtime_common import ROOT
from quality_metrics import density_summary,timing_summary

def offset(a):return np.array([0 if a==2 else .5,0 if a==1 else .5,0 if a==0 else .5],np.float32)[:,None,None,None]
def lattice(shape,a):return np.indices(shape,dtype=np.float32)+offset(a)
def sample(a,p,axis):
    r=map_coordinates(a,p-offset(axis),order=1,mode='nearest',prefilter=False)
    if axis==3:
        for i,n in enumerate(a.shape):r[(p[i]<0)|(p[i]>n)]=0
    return r

def velocity(v,p):return np.stack([sample(v[i],p,i) for i in (2,1,0)])
def trace(v,p,dt):return p-dt*velocity(v,p-.5*dt*velocity(v,p))
def advect(a,v,p,axis,dt):
    back=trace(v,p,dt);forward=trace(v,p,-dt);pred=sample(a,back,axis);q=pred+.5*(a-sample(pred,forward,axis));b=np.floor(back-offset(axis)).astype(np.int32)
    lo=np.full(a.shape,np.inf,np.float32);hi=-lo.copy()
    for z in (0,1):
      for y in (0,1):
        for x in (0,1):
          u=a[np.clip(b[0]+z,0,a.shape[0]-1),np.clip(b[1]+y,0,a.shape[1]-1),np.clip(b[2]+x,0,a.shape[2]-1)];lo=np.minimum(lo,u);hi=np.maximum(hi,u)
    r=pred+np.minimum(1.,2/np.maximum(1.,np.sqrt(np.sum((back-p)**2,axis=0))))*(np.clip(q,lo,hi)-pred)
    if axis==3:
        for i,n in enumerate(a.shape):r[(back[i]<0)|(back[i]>n)]=0
        r=np.maximum(r,0.)
    return r.astype(np.float32)

def divergence(v,dx):return (np.diff(v[0],axis=2)+np.diff(v[1],axis=1)+np.diff(v[2],axis=0))/dx
def project(v,dx,eigen):
    # Open boundary: outward extrapolation BEFORE projection only.
    for a,u in enumerate(v):
        w=np.moveaxis(u,2-a,0);w[0]=np.minimum(0,w[1]);w[-1]=np.maximum(0,w[-2])
    div=divergence(v,dx);before=float(np.sqrt(np.mean(div.astype(np.float64)**2)))
    p=idstn(dstn(div.astype(np.float64)*dx*dx,type=1,norm='ortho')/eigen,type=1,norm='ortho')
    for a in range(3):
        pads=[(0,0)]*3;pads[2-a]=(1,1);v[a]-=(np.diff(np.pad(p,pads),axis=2-a)/dx).astype(np.float32)
    return before,float(np.sqrt(np.mean(divergence(v,dx).astype(np.float64)**2)))

def weights(p,e,dx,axis):
    q=np.moveaxis(p,0,-1)[...,::-1]*dx-np.asarray(e['position']);along=q@axis;rad=np.linalg.norm(q-along[...,None]*axis,axis=-1);r=max(e['radius'],1.1*dx);l=max(e['length'] or e['radius'],dx)
    def sm(x):x=np.clip(x,0,1);return x*x*(3-2*x)
    return ((1-sm(rad/r))*sm((along+.5*dx)/dx)*sm((l+.5*dx-along)/dx)).astype(np.float32)

def profile(p):
    if not p:return None
    a=np.asarray(p['points'],np.float64);x=a[:,0];y=a[:,1:];d=np.diff(y,axis=0)/np.diff(x)[:,None];m=np.zeros_like(y);m[0]=d[0];m[-1]=d[-1];m[1:-1]=np.where(d[:-1]*d[1:]>0,(d[:-1]+d[1:])*.5,0)
    for i in range(len(d)):
        for j in range(d.shape[1]):
            if abs(d[i,j])<1e-9:m[i,j]=m[i+1,j]=0;continue
            u=m[i,j]/d[i,j];v=m[i+1,j]/d[i,j];s=u*u+v*v
            if s>9:k=3/np.sqrt(s);m[i,j]=k*u*d[i,j];m[i+1,j]=k*v*d[i,j]
    return CubicHermiteSpline(x,y,m)

class Reference:
    def __init__(self,preset,quality,turbulence=False):
        self.turbulence=turbulence;self.e=preset['emitter'];self.p=preset['profile'];self.curve=profile(self.p);c=self.c=dict(preset['config']);q={'low':.5,'medium':1,'high':2}[quality];c['cells']=[int(n*q) for n in c['cells']];c['cellSize']/=q;self.dx=c['cellSize'];self.dt=c['fixedDt'];self.ticks=0;self.clamps=0
        nx,ny,nz=c['cells'];s=(nz,ny,nx);self.rho=np.zeros(s,np.float32);self.temp=self.rho.copy();self.v=[np.zeros((nz+int(a==2),ny+int(a==1),nx+int(a==0)),np.float32) for a in range(3)];self.p0=lattice(s,3);self.pv=[lattice(u.shape,a) for a,u in enumerate(self.v)]
        self.axis=np.asarray(self.e['direction'],dtype=np.float64);self.axis/=np.linalg.norm(self.axis);self.w=[weights(p,self.e,self.dx,self.axis) for p in [*self.pv,self.p0]];r=self.e['radius'];l=self.e['length'] or r;self.scale=(r/max(r,self.dx*1.1))**2*l/max(l,self.dx)
        # Experimental resolved forcing, applied to velocity BEFORE projection,
        # never to rendered density. Polarization is perpendicular to each wave
        # vector; the local plume mask can introduce divergence, which is projected.
        # Coherent spatial phase and temporal frequency (not frame-random jitter).
        self.modes=[]
        if turbulence:
            smoke=preset['key']=='cigarette_smoke';rng=np.random.default_rng(137 if smoke else 241)
            scale=.065 if smoke else .17;self.acceleration=2.3 if smoke else 4.5;self.onset=.045 if smoke else .08;self.rho_ref=.035 if smoke else .28
            k=rng.normal(size=(6,3));k/=np.linalg.norm(k,axis=1,keepdims=True);pol=np.cross(k,rng.normal(size=(6,3)));pol/=np.linalg.norm(pol,axis=1,keepdims=True)
            wave_lengths=scale*np.array([1.5,1.,1.,.72,.72,.50]);omega=2*np.pi*np.array([.61,.87,-.72,1.3,-1.1,.45]);phase=rng.uniform(-np.pi,np.pi,6)
            for a,p in enumerate(self.pv):
                xyz=np.moveaxis(p,0,-1)[...,::-1]*self.dx-np.array(self.e['position']);along=xyz@self.axis;grow=np.clip((along-self.onset)/(self.onset*2),0,1);grow=grow*grow*(3-2*grow)
                arg=np.einsum('...j,kj->k...',xyz,k)*(2*np.pi/wave_lengths)[:,None,None,None]+phase[:,None,None,None]
                # Amplitudes sum to <=1; peak acceleration is explicitly bounded.
                amps=pol[:,a]*np.array([.25,.20,.20,.14,.13,.08]);self.modes.append((np.sin(arg).astype(np.float32),np.cos(arg).astype(np.float32),amps,omega,grow.astype(np.float32)))
        ez,ey,ex=[2*np.cos(np.pi*np.arange(1,n+1)/(n+1))-2 for n in s];self.eigen=ez[:,None,None]+ey[None,:,None]+ex[None,None,:]
    def step(self):
        c=self.c;dt=self.dt;dx=self.dx;age=self.ticks*dt;active=not self.p or age<self.p['duration'];speed=self.e['speed'];rate=self.e['densityRate'];temp=self.e['temperature']
        if self.curve is not None and active:
            f=self.curve(age/self.p['duration']);speed*=f[0];rate*=np.clip(f[1],0,1)*max(0.,f[2])
        for a,v in enumerate(self.v):
            v+=(c['wind'][a]-v)*(1-np.exp(-c['drag']*dt))
            if a==1:v+=dt*(c['buoyancy']*sample(self.temp,self.pv[a],3)-c['densityWeight']*sample(self.rho,self.pv[a],3))
            if active:v+=(self.axis[a]*speed-v)*(1-np.exp(-20*self.w[a]*dt))
            if self.turbulence:
                ss,cc,amp,omega,grow=self.modes[a];phase=omega*age
                field=np.einsum('k,k...->...',amp*np.cos(phase),ss)+np.einsum('k,k...->...',amp*np.sin(phase),cc)
                mask=np.sqrt(np.clip(sample(self.rho,self.pv[a],3)/self.rho_ref,0,1))*grow
                v+=dt*self.acceleration*mask*field.astype(np.float32)
        # Centred curl and confinement; force averaged onto MAC faces.
        u=(self.v[0][...,:-1]+self.v[0][...,1:])*.5;v=(self.v[1][:,:-1,:]+self.v[1][:,1:,:])*.5;w=(self.v[2][:-1,...]+self.v[2][1:,...])*.5
        curl=np.stack((np.gradient(w,dx,axis=1)-np.gradient(v,dx,axis=0),np.gradient(u,dx,axis=0)-np.gradient(w,dx,axis=2),np.gradient(v,dx,axis=2)-np.gradient(u,dx,axis=1)),axis=-1)
        mag=np.linalg.norm(curl,axis=-1);gz,gy,gx=np.gradient(mag,dx);g=np.stack((gx,gy,gz),axis=-1);force=np.cross(g/(np.linalg.norm(g,axis=-1,keepdims=True)+1e-6),curl)*c['vorticity']*dx
        force[[0,-1],:,:,:]=0;force[:,[0,-1],:,:]=0;force[:,:,[0,-1],:]=0
        for a,v in enumerate(self.v):
            axis=2-a;f=np.moveaxis(force[...,a],axis,0);vv=np.moveaxis(v,axis,0);vv[1:-1]+=.5*dt*(f[:-1]+f[1:]);self.clamps+=int(np.count_nonzero(np.abs(v)>c['maxVelocity']));np.clip(v,-c['maxVelocity'],c['maxVelocity'],out=v)
        self.v=[advect(v,self.v,p,a,dt/dx) for a,(v,p) in enumerate(zip(self.v,self.pv))];before,after=project(self.v,dx,self.eigen)
        for v in self.v:self.clamps+=int(np.count_nonzero(np.abs(v)>c['maxVelocity']));np.clip(v,-c['maxVelocity'],c['maxVelocity'],out=v)
        self.advance_scalars(active,rate,temp);self.ticks+=1
        return before,after
    def advance_scalars(self,active,rate,temp):
        c=self.c;dt=self.dt;dx=self.dx
        self.rho=advect(self.rho,self.v,self.p0,3,dt/dx)*np.exp(-c['densityDecay']*dt);self.temp=advect(self.temp,self.v,self.p0,3,dt/dx)*np.exp(-c['cooling']*dt)
        if active:self.rho+=rate*self.w[3]*self.scale*dt;self.temp+=np.maximum(temp-self.temp,0)*(1-np.exp(-20*self.w[3]*dt))
        np.clip(self.rho,0,c['densityCap'],out=self.rho)

def run_case(preset,quality,ticks,output,turbulence=False):
    s=Reference(preset,quality,turbulence);c=s.c;e=s.e;extent=[n*s.dx for n in c['cells']];rows=[];times=[]
    for tick in range(1,max(ticks)+1):
        t=time.perf_counter();before,after=s.step();times.append((time.perf_counter()-t)*1000)
        if tick not in ticks:continue
        if not all(np.isfinite(a).all() for a in [s.rho,s.temp,*s.v]):raise RuntimeError('nonfinite reference state')
        key=f"{preset['key']}-{quality}-{tick:04d}";spec=dict(key=key,turbulence=turbulence,effect=preset['key'],cells=c['cells'],extent=extent,densityCap=c['densityCap'],material=preset['material'],time=tick*s.dt,source=e['position'],direction=s.axis.tolist(),evidence='Independent SciPy MAC CPU reference, spectral pressure; NOT Rust runtime')
        (output/(key+'.json')).write_text(json.dumps(spec,indent=2)+'\n');s.rho.astype('<f4').tofile(output/(key+'.density.f32'));s.temp.astype('<f4').tofile(output/(key+'.temperature.f32'))
        summary=density_summary(s.rho,cells=c['cells'],extent=extent,cap=c['densityCap'],source=e['position'],direction=s.axis);rows.append(dict(key=key,tick=tick,seconds=tick*s.dt,divergence_before=before,divergence_after=after,clamps=s.clamps,**summary));print(key,summary['density_integral'],summary['plume'],f'div {before:.3g}->{after:.3g}',flush=True)
    if not any(r['density_integral']>0 for r in rows):raise RuntimeError('empty source run')
    return dict(effect=preset['key'],quality=quality,turbulence=turbulence,config=c,frames=rows,step_timing=timing_summary(times))

def main():
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('--quality',choices=['low','medium','high'],default='medium');a.add_argument('--effects',nargs='+',choices=['cigarette_smoke','exhaled_aerosol'],default=['cigarette_smoke','exhaled_aerosol']);a.add_argument('--ticks',nargs='+',type=int,default=[30,60,120,180]);a.add_argument('--turbulence',action='store_true',help='experimental coherent force in the independent solver only');a.add_argument('--output',type=Path,default=ROOT/'reports/local/lab/reference-fluid');args=a.parse_args()
    if not args.ticks or any(t<1 or t>600 for t in args.ticks):a.error('ticks must be 1..600')
    presets={p['key']:p for p in json.loads((ROOT/'effects/presets.json').read_text())['presets']};args.output.mkdir(parents=True,exist_ok=True);path=args.output/'reference.json';path.write_text(json.dumps({'status':'RUNNING','evidence':'Independent CPU reference, not Rust'}))
    try:
        rows=[run_case(presets[k],args.quality,sorted(set(args.ticks)),args.output,args.turbulence) for k in args.effects];path.write_text(json.dumps(dict(status='PASS',evidence='Independent actual open MAC CPU reference; spectral projection, no Rust parity/engine certification',implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),results=rows),indent=2)+'\n')
    except Exception as ex:path.write_text(json.dumps({'status':'FAIL','error':str(ex)},indent=2));raise
if __name__=='__main__':main()
