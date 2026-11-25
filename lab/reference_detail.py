"""Independent multiresolution scalar transport experiment, NOT native SDK runtime.
Medium-grid MAC pressure/velocity plus independently integrated 4x scalar density and
heat; coarse/fine source integral matched. Optional curl of a spatial vector
potential supplies small-scale kinematic motion, not a second pressure solver.
Requires NumPy, SciPy, Numba. No field interpolation is used as the output.
"""
from pathlib import Path
import argparse,hashlib,json,time
import numpy as np
from numba import njit,prange,set_num_threads
import bootstrap  # enables explicit shared validation helpers
from reference_fluid import Reference,weights,lattice
from quality_metrics import density_summary,timing_summary
from runtime_common import ROOT

@njit(inline='always')
def trilerp(a,x,y,z):
    nz,ny,nx=a.shape
    x=max(0.,min(nx-1.,x));y=max(0.,min(ny-1.,y));z=max(0.,min(nz-1.,z))
    i=int(x);j=int(y);k=int(z);ii=min(i+1,nx-1);jj=min(j+1,ny-1);kk=min(k+1,nz-1)
    u=x-i;v=y-j;w=z-k
    return ((a[k,j,i]*(1-u)+a[k,j,ii]*u)*(1-v)+(a[k,jj,i]*(1-u)+a[k,jj,ii]*u)*v)*(1-w)+((a[kk,j,i]*(1-u)+a[kk,j,ii]*u)*(1-v)+(a[kk,jj,i]*(1-u)+a[kk,jj,ii]*u)*v)*w

@njit(parallel=True)
def velocity(u,v,w,detail,basis,coeff,scale,dx):
    nz,ny,nx=detail.shape[1:]
    for z in prange(nz):
      for y in range(ny):
       for x in range(nx):
        px=(x+.5)/scale;py=(y+.5)/scale;pz=(z+.5)/scale
        a=trilerp(u,px,py-.5,pz-.5);b=trilerp(v,px-.5,py,pz-.5);c=trilerp(w,px-.5,py-.5,pz)
        for m in range(len(coeff)):
            a+=coeff[m]*basis[m,0,z,y,x];b+=coeff[m]*basis[m,1,z,y,x];c+=coeff[m]*basis[m,2,z,y,x]
        detail[0,z,y,x]=a/dx;detail[1,z,y,x]=b/dx;detail[2,z,y,x]=c/dx

@njit(inline='always')
def trace(vel,x,y,z,dt):
    ax=vel[0,z,y,x];ay=vel[1,z,y,x];az=vel[2,z,y,x]
    mx=x-.5*dt*ax;my=y-.5*dt*ay;mz=z-.5*dt*az
    return (x-dt*trilerp(vel[0],mx,my,mz),y-dt*trilerp(vel[1],mx,my,mz),z-dt*trilerp(vel[2],mx,my,mz))

@njit(inline='always')
def scalar(a,x,y,z):
    nz,ny,nx=a.shape
    if x<-.5 or y<-.5 or z<-.5 or x>nx-.5 or y>ny-.5 or z>nz-.5:return 0.
    return trilerp(a,x,y,z)

@njit(inline='always')
def bounds(a,x,y,z):
    nz,ny,nx=a.shape;i=int(np.floor(x));j=int(np.floor(y));k=int(np.floor(z));lo=1e30;hi=-1e30
    for dz in range(2):
     for dy in range(2):
      for dx in range(2):
       q=a[max(0,min(nz-1,k+dz)),max(0,min(ny-1,j+dy)),max(0,min(nx-1,i+dx))];lo=min(lo,q);hi=max(hi,q)
    return lo,hi

@njit(parallel=True)
def transport(rho,temp,vel,pred,pt,output,ot,source,dt,decay,cool,density_cap,rate,heat):
    nz,ny,nx=rho.shape
    # Forward semi-Lagrangian prediction for both physical scalars.
    for z in prange(nz):
      for y in range(ny):
       for x in range(nx):
        a,b,c=trace(vel,x,y,z,dt);pred[z,y,x]=scalar(rho,a,b,c);pt[z,y,x]=scalar(temp,a,b,c)
    # Reverse prediction, bounded MacCormack, exponential decay, source.
    for z in prange(nz):
      for y in range(ny):
       for x in range(nx):
        a,b,c=trace(vel,x,y,z,dt);u,v,w=trace(vel,x,y,z,-dt)
        if a<-.5 or b<-.5 or c<-.5 or a>nx-.5 or b>ny-.5 or c>nz-.5:r=0.;t=0.
        else:
         lo,hi=bounds(rho,a,b,c);lt,ht=bounds(temp,a,b,c)
         r=max(lo,min(hi,pred[z,y,x]+.5*(rho[z,y,x]-scalar(pred,u,v,w))))
         t=max(lt,min(ht,pt[z,y,x]+.5*(temp[z,y,x]-scalar(pt,u,v,w))))
        s=source[z,y,x];output[z,y,x]=min(density_cap,max(0.,r*decay+rate*s*dt));ot[z,y,x]=max(0.,t*cool+max(0.,heat-t*cool)*(1-np.exp(-20*s*dt)))

class Fine:
    def __init__(self,s,scale,seed):
        self.s=s;self.scale=scale;self.dx=s.dx/scale;self.cells=[n*scale for n in s.c['cells']];shape=tuple(reversed(self.cells));self.rho=np.zeros(shape,np.float32);self.temp=self.rho.copy();self.pred=self.rho.copy();self.pt=self.rho.copy();self.out=self.rho.copy();self.ot=self.rho.copy();self.vel=np.zeros((3,*shape),np.float32)
        p=lattice(shape,3);self.source=weights(p,s.e,self.dx,s.axis);target=float(np.sum(s.w[3],dtype=np.float64)*s.scale*s.dx**3);actual=float(np.sum(self.source,dtype=np.float64)*self.dx**3);self.injection_scale=target/actual
        # Curl of two pairs of vector potentials; the spatial mask is inside curl,
        # so localizing the waves does not itself introduce divergence. Detail is
        # velocity, never an artificial noise multiplied into the density/render.
        xyz=np.moveaxis(p,0,-1)[...,::-1]*self.dx-np.array(s.e['position']);along=xyz@s.axis;rad=np.linalg.norm(xyz-along[...,None]*s.axis,axis=-1);smoke=s.e['radius']<.015;onset=.025 if smoke else .065;spread=(.013 if smoke else .060)+np.maximum(along,0)*(.32 if smoke else .25);grow=np.clip((along-onset)/max(onset,1e-6),0,1);grow=grow*grow*(3-2*grow)
        mask=grow*np.exp(-.5*(rad/np.maximum(spread,self.dx))**2);mask*=np.clip((shape[2]-p[2])/4,0,1)*np.clip(p[2]/4,0,1)*np.clip((shape[1]-p[1])/4,0,1)*np.clip(p[1]/4,0,1)*np.clip((shape[0]-p[0])/4,0,1)*np.clip(p[0]/4,0,1)
        rng=np.random.default_rng(seed);basis=[];self.frequencies=np.array([1.3,-2.1])*2*np.pi
        for wave in ([.022,.014] if smoke else [.065,.042]):
            direction=rng.normal(size=3);direction/=np.linalg.norm(direction);pol=rng.normal(size=3);pol/=np.linalg.norm(pol);arg=(xyz@direction)*(2*np.pi/wave)+rng.uniform(-np.pi,np.pi)
            for f in [np.sin,np.cos]:
                psi=(mask*f(arg)*wave/(2*np.pi)).astype(np.float32);gz,gy,gx=np.gradient(psi,self.dx);curl=np.stack((gy*pol[2]-gz*pol[1],gz*pol[0]-gx*pol[2],gx*pol[1]-gy*pol[0]));basis.append(curl.astype(np.float32))
        self.basis=np.stack(basis);self.amplitude=.10 if smoke else .24
    def step(self):
        s=self.s;age=s.ticks*s.dt;active=not s.p or age<s.p['duration'];rate=s.e['densityRate'] if active else 0.;heat=s.e['temperature'] if active else 0.
        if s.curve is not None and active:
            f=s.curve(age/s.p['duration']);rate*=np.clip(f[1],0,1)*max(0.,f[2])
        s.step();phase=self.frequencies*age;coeff=(self.amplitude*np.stack((np.cos(phase),np.sin(phase)),axis=1).ravel()).astype(np.float32)
        velocity(*s.v,self.vel,self.basis,coeff,self.scale,self.dx)
        transport(self.rho,self.temp,self.vel,self.pred,self.pt,self.out,self.ot,self.source,s.dt,np.exp(-s.c['densityDecay']*s.dt),np.exp(-s.c['cooling']*s.dt),s.c['densityCap'],rate*self.injection_scale,heat)
        self.rho,self.out=self.out,self.rho;self.temp,self.ot=self.ot,self.temp

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--scale',type=int,choices=[2,3,4],default=4);p.add_argument('--ticks',type=int,default=120);p.add_argument('--output',type=Path,default=ROOT/'reports/local/lab/fidelity/reference-detail');p.add_argument('--threads',type=int,default=4);args=p.parse_args();set_num_threads(args.threads)
    if not 1<=args.ticks<=600:p.error('ticks 1..600')
    data=json.loads((ROOT/'effects/presets.json').read_text());args.output.mkdir(parents=True,exist_ok=True);path=args.output/'reference.json';path.write_text(json.dumps({'status':'RUNNING'}));rows=[]
    try:
      for key in ['cigarette_smoke','exhaled_aerosol']:
        preset=next(x for x in data['presets'] if x['key']==key);s=Reference(preset,'medium',True);f=Fine(s,args.scale,412 if key=='cigarette_smoke' else 819);times=[]
        for i in range(args.ticks):
            start=time.perf_counter();f.step();times.append((time.perf_counter()-start)*1000)
        if not np.isfinite(f.rho).all() or not np.isfinite(f.temp).all() or not np.any(f.rho>0):raise RuntimeError('invalid detail output')
        name=f'{key}-detail-{args.ticks:04d}';extent=[n*f.dx for n in f.cells];spec=dict(key=name,effect=key,cells=f.cells,extent=extent,densityCap=s.c['densityCap'],material=preset['material'],time=s.ticks*s.dt,source=s.e['position'],direction=s.axis.tolist(),evidence='Actual independent CPU multiresolution scalar transport; coarse SciPy MAC + fine kinematic curl detail; NOT Rust or GPU')
        (args.output/(name+'.json')).write_text(json.dumps(spec,indent=2));f.rho.astype('<f4').tofile(args.output/(name+'.density.f32'));f.temp.astype('<f4').tofile(args.output/(name+'.temperature.f32'));a=density_summary(f.rho,cells=f.cells,extent=extent,cap=s.c['densityCap'],source=s.e['position'],direction=s.axis);rows.append(dict(key=key,cells=f.cells,coarse_cells=s.c['cells'],time=spec['time'],source_integral_matched=True,injection_scale=f.injection_scale,step_timing_including_jit=timing_summary(times),coarse_velocity_clamps=s.clamps,**a));print(key,a['plume'],flush=True)
      path.write_text(json.dumps(dict(status='PASS',evidence=spec['evidence'],implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),results=rows),indent=2)+'\n')
    except Exception as e:path.write_text(json.dumps(dict(status='FAIL',error=str(e))));raise
if __name__=='__main__':main()
