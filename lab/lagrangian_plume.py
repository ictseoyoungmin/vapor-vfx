"""Reduced-order full-domain VFX experiment, NOT a Navier-Stokes solver.
A prescribed axisymmetric entraining streamfunction plus convected, offset
vortex rings advects Lagrangian scalar markers (RK2). A volume-preserving
centerline warp breaks symmetry. Conservative scalar deposition is independent
of optical settings; no image-space smoke/noise. No automatic SDK fallback.
"""
from __future__ import annotations
import argparse, json, math, time
from pathlib import Path
import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.ndimage import gaussian_filter
from numba import njit, prange, set_num_threads
import bootstrap
from runtime_common import ROOT, sha256
from check_sdk import atomic_report
from quality_metrics import density_summary, timing_summary

CASES={
 'cigarette_smoke':dict(cells=[80,192,80],extent=[.40,.96,.40],source=[.20,.035,.20],spread=.085,length=.22,conv=.20,period=.29,warp=.038,sigma=.85),
 'exhaled_aerosol':dict(cells=[160,80,80],extent=[2.4,1.2,1.2],source=[.12,.48,.60],spread=.13,length=.204,conv=.90,period=.14,warp=.045,sigma=.9),
}
@njit(inline='always')
def sat(x):return max(0.,min(1.,x))
@njit(inline='always')
def smooth(x):
    x=sat(x);return x*x*(3.-2.*x)
@njit(inline='always')
def interpolate(table,t,dt):
    if t<0 or t>dt*(len(table)-1):return 0.,0.
    i=min(len(table)-2,int(t/dt));f=t/dt-i
    return table[i,0]*(1-f)+table[i+1,0]*f,table[i,1]*(1-f)+table[i+1,1]*f
@njit(inline='always')
def warp(s,t,amp,smoke):
    # x'=x-c(s,t), z'=z-d(s,t); determinant = 1.
    start=.035 if smoke else .05;length=.22 if smoke else .44
    h=max(0.,s-start);a=amp*(1.-math.exp(-(h/length)**2));da=amp*2*h/(length*length)*math.exp(-(h/length)**2)
    k=24. if smoke else 9.;w=2.1 if smoke else 2.8
    p=k*s-w*t+.7;q=.63*k*s-1.31*w*t+2.1
    x=a*math.sin(p);z=.74*a*math.sin(q)
    return x,z,da*math.sin(p)+a*k*math.cos(p),.74*(da*math.sin(q)+a*.63*k*math.cos(q)),-a*w*math.cos(p),-.74*a*1.31*w*math.cos(q)
@njit(inline='always')
def velocity(s,x,z,t,par,rings,table,table_dt,model):
    r0,u0,spread,L,amp,smoke=par
    h=max(0.,s);b=r0+spread*h;db=spread if s>0 else 0.
    if smoke:
        # A buoyant-plume velocity envelope (empirical, not buoyancy force solve).
        us=u0+0.105*(1.-math.exp(-h/.035));du=3.*math.exp(-h/.035) if s>0 else 0.
        if model==2:
            # Empirical buoyant-plume envelope decelerates after transition.
            q=1+max(0.,h-.065)/.20;du=du/q**.42-(.42*us/(.20*q**1.42) if h>.065 else 0.);us/=q**.42
        f=1.;fs=0.
    else:
        us=u0/(1+h/L);du=-u0/L/(1+h/L)**2 if s>0 else 0.
        travel=(h+.5*h*h/L)/u0
        f,df=interpolate(table,t-travel,table_dt);fs=-df*(1+h/L)/u0 if s>0 else 0.
    if model:
        cx,cz,dxs,dzs,dxt,dzt=warp(h,t,amp,smoke);x-=cx;z-=cz
    else:dxs=dzs=dxt=dzt=0.
    r2=x*x+z*z;e=math.exp(-r2/(b*b));K=.5*us*b*b;dK=.5*du*b*b+us*b*db
    axial=us*f*e
    # u_r/r, analytic axis limit, from -d(psi)/ds / r².
    ratio=1/(b*b) if r2<1e-12 else -math.expm1(-r2/(b*b))/r2
    radial=-(dK*f+K*fs)*ratio+2*K*f*db*e/(b**3)
    vx=radial*x;vz=radial*z
    if model:
        # Compact-ish smooth ring contribution from psi=A*r²*exp(-Q/2).
        # Ring axes are parallel in local coordinates, but centres offset by seed.
        for j in range(rings.shape[0]):
            sc,rx,rz,R,a_s,a_r,A,angle=rings[j];ds=s-sc
            if abs(ds)>3.8*a_s:continue
            xx=x-rx;zz=z-rz;rr=xx*xx+zz*zz;Q=(rr-R*R)/(2*R*a_r)
            q=(ds/a_s)**2+Q*Q
            if q>36.:continue
            v=A*math.exp(-.5*q)
            axial+=v*(2.-rr*Q/(R*a_r))
            k=v*ds/(a_s*a_s);vx+=k*xx;vz+=k*zz
            if model==2:
                # Non-axisymmetric coherent eddies in a plane through the jet;
                # psi=A*a*exp(-distance²/2a²), zero perpendicular velocity.
                ca=math.cos(angle);sa=math.sin(angle);q1=xx*ca+zz*sa;q2=-xx*sa+zz*ca
                a=R*1.25;wq=(ds/a)**2+(q1/a)**2+(q2/(1.4*a))**2
                if wq<25:
                    # Alternating circulation, transition envelope suppresses near-source mixing.
                    amp2=A*(6.5 if smoke else 5.5)*math.exp(-.5*wq)*smooth((sc-(.035 if smoke else .06))/(.06 if smoke else .12))
                    sign=1. if j%2==0 else -1.
                    axial-=sign*amp2*q1/a;turn=sign*amp2*ds/a;vx+=turn*ca;vz+=turn*sa
        # Volume-preserving map from moving coordinates to world coordinates.
        vx+=dxt+dxs*axial;vz+=dzt+dzs*axial
    return axial,vx,vz
@njit(parallel=True,cache=True)
def advect_markers(q,t,dt,par,r0,r1,table,td,model):
    out=np.empty_like(q)
    for i in prange(len(q)):
        s,x,z=q[i];a,b,c=velocity(s,x,z,t,par,r0,table,td,model)
        a,b,c=velocity(s+.5*dt*a,x+.5*dt*b,z+.5*dt*c,t+.5*dt,par,r1,table,td,model)
        out[i,0]=s+dt*a;out[i,1]=x+dt*b;out[i,2]=z+dt*c
    return out
@njit(cache=True)
def cic(points,mass,temp,cells,extent):
    nx,ny,nz=cells;dx=extent[0]/nx;dy=extent[1]/ny;dz=extent[2]/nz
    d=np.zeros((nz,ny,nx),np.float64);h=np.zeros_like(d);lost=0.
    for j in range(len(points)):
        x=points[j,0]/dx-.5;y=points[j,1]/dy-.5;z=points[j,2]/dz-.5;ix=math.floor(x);iy=math.floor(y);iz=math.floor(z);fx=x-ix;fy=y-iy;fz=z-iz
        for k in range(2):
         for l in range(2):
          for i in range(2):
            a=ix+i;b=iy+l;c=iz+k;w=mass[j]*(fx if i else 1-fx)*(fy if l else 1-fy)*(fz if k else 1-fz)
            if 0<=a<nx and 0<=b<ny and 0<=c<nz:d[c,b,a]+=w;h[c,b,a]+=w*temp[j]
            else:lost+=w
    return d,h,lost

def deposition(points,mass,temp,cells,extent,sigma,cap):
    d,h,lost=cic(points,mass,temp,np.array(cells),np.array(extent));before=float(d.sum());d=gaussian_filter(d,sigma,mode='constant',truncate=3.);h=gaussian_filter(h,sigma,mode='constant',truncate=3.)
    deposited=float(d.sum());lost+=before-deposited;dv=float(np.prod(np.array(extent)/cells));rho=d/dv;heat=np.divide(h,d,out=np.zeros_like(h),where=d>1e-20);clamped=np.minimum(rho,cap);sat_mass=float(np.sum(rho-clamped)*dv)
    return clamped.astype(np.float32),heat.astype(np.float32),dict(particle_mass=float(mass.sum()),deposition_loss=lost,saturation=sat_mass,grid_mass=float(clamped.sum()*dv),closure=float(clamped.sum()*dv)-(float(mass.sum())-lost-sat_mass))

def basis(direction):
    axis=np.array(direction,dtype=float);axis/=np.linalg.norm(axis);u=np.cross(axis,[0,1,0] if abs(axis[1])<.9 else [1,0,0]);u/=np.linalg.norm(u);return np.stack([axis,u,np.cross(axis,u)])

class Plume:
    def __init__(self,preset,model='rings',seed=43,markers=320):
        self.preset=preset;self.e=preset['emitter'];self.c=preset['config'];self.case=CASES[preset['key']];self.smoke=preset['key']=='cigarette_smoke';self.model={'base':0,'rings':1,'packets':2}[model];self.seed=seed;self.markers=markers;self.rng=np.random.default_rng(seed);self.dispersion_rng=np.random.default_rng(seed+173);self.dt=1/60;self.t=0.;self.q=np.empty((0,3));self.mass=np.empty(0);self.birth=np.empty(0);self.eddy=np.empty((0,3));self.injected=0.;self.decayed=0.;self.outflow=0.;self.B=basis(self.e['direction']);self.source=np.array(self.case['source']);r=self.e['radius'];L=self.case['length'];self.par=np.array([r,self.e['speed'],self.case['spread'],L,self.case['warp'],float(self.smoke)]);l=self.e['length'];self.analytic=.3*np.pi*r*r*(l-min(r*.5,l*.25));self.profile=preset.get('profile');self.duration=4. if self.smoke else self.profile['duration'];self.td=.0025
        grid=np.arange(0,self.duration+self.td*.5,self.td)
        if self.smoke:self.table=np.column_stack((np.ones(len(grid)),np.zeros(len(grid))));self.curves=None
        else:
            pp=np.array(self.profile['points']);self.curves=PchipInterpolator(pp[:,0]*self.duration,pp[:,1:],axis=0,extrapolate=False);self.table=np.column_stack((self.curves(grid)[:,0],self.curves.derivative()(grid)[:,0]));self.table=np.nan_to_num(self.table)
        rng=np.random.default_rng(seed+100);period=self.case['period'];times=np.arange(.04,self.duration,period);self.ring_birth=times+rng.uniform(-period*.12,period*.12,len(times));self.ring_phase=rng.uniform(0,2*np.pi,len(times));self.ring_gain=rng.uniform(.65,1.15,len(times))
    def rings(self,t):
        age=t-self.ring_birth;mask=(age>=0)&(age<4.);a=age[mask];phase=self.ring_phase[mask];gain=self.ring_gain[mask];r=self.e['radius'];L=self.case['length'];speed=self.case['conv'];s=self.e['length']*.65+L*(np.sqrt(1+2*speed*a/L)-1) if not self.smoke else self.e['length']*.65+speed*a
        R=r+self.case['spread']*s;offset=R*(.18+.12*np.sin(1.7*a));as_=R*.85;ar=R*.54;A=(.17 if self.smoke else .21)*speed/(1+s/L)*gain*np.exp(-a/(2.4 if self.smoke else 1.8));A*=np.minimum(1.,a/.06)
        if not self.smoke:
            birth=self.ring_birth[mask];A*=np.clip(self.curves(birth)[:,0],0,1)
        return np.column_stack((s,offset*np.cos(phase),offset*np.sin(phase),R,as_,ar,A,phase))
    def advance(self):
        dt=self.dt;t=self.t;age=t+dt*.5;rate=self.e['densityRate'];active=age<self.duration
        if active and self.curves is not None:
            profile=self.curves(age);rate*=max(0.,float(profile[1]))*max(0.,float(profile[2]))
        # Scalar marker weight is the physical source integral, independent of grid.
        before=float(self.mass.sum());self.mass*=math.exp(-self.c['densityDecay']*dt);self.decayed+=before-float(self.mass.sum())
        if active and rate>0:
            n=self.markers;u=self.rng.random((n,3));r=self.e['radius'];l=self.e['length'];s=u[:,0]*l;rad=np.sqrt(u[:,1]);phi=u[:,2]*2*np.pi;taper=min(r*.5,l*.25)
            sm=lambda x:np.clip(x,0,1)**2*(3-2*np.clip(x,0,1));w=(1-sm(rad))*sm(s/taper)*sm((l-s)/taper);m=rate*self.analytic*dt;w*=m/w.sum();self.injected+=m
            new=np.column_stack((s,r*rad*np.cos(phi),r*rad*np.sin(phi)));self.q=np.concatenate((self.q,new));self.mass=np.concatenate((self.mass,w));self.birth=np.concatenate((self.birth,np.full(n,age)));self.eddy=np.concatenate((self.eddy,np.zeros((n,3))))
        if len(self.q):
            self.q=advect_markers(self.q,t,dt,self.par,self.rings(t),self.rings(age),self.table,self.td,self.model)
            if self.model==2:
                # Optional correlated subgrid dispersion of scalar markers. It is
                # a stochastic transport approximation, not resolved momentum.
                h=np.maximum(0.,self.q[:,0]);b=self.e['radius']+self.case['spread']*h
                vel=self.case['conv']/(1+h/self.case['length'])**(.4 if self.smoke else .7)
                transition=np.clip((h-(.035 if self.smoke else .06))/(.10 if self.smoke else .20),0,1)
                tau=np.maximum(.035,.7*b/np.maximum(vel,.04));memory=np.exp(-dt/tau)
                # Effective eddy diffusivity, D = variance * correlation time.
                diffusivity=(.10 if self.smoke else .18)*b*vel*transition
                std=np.sqrt(diffusivity/tau);self.eddy=self.eddy*memory[:,None]+self.dispersion_rng.normal(size=self.eddy.shape)*(std*np.sqrt(1-memory*memory))[:,None]
                self.q+=dt*self.eddy
            world=self.source+self.q@self.B
            inside=np.all((world>=0)&(world<=self.case['extent']),axis=1);self.outflow+=float(self.mass[~inside].sum());self.q=self.q[inside];self.mass=self.mass[inside];self.birth=self.birth[inside];self.eddy=self.eddy[inside]
        self.t+=dt
    def field(self):
        p=self.source+self.q@self.B;temp=self.e['temperature']*np.exp(-self.c['cooling']*(self.t-self.birth));d,h,b=deposition(p,self.mass,temp,self.case['cells'],self.case['extent'],self.case['sigma'],self.c['densityCap']);b.update(injected=self.injected,decayed=self.decayed,escaped=self.outflow,particle_closure=float(self.mass.sum())-(self.injected-self.decayed-self.outflow));return d,h,b

def run(preset,model,seconds,out,markers):
    s=Plume(preset,model,markers=markers);rows=[];times=[];steps=round(seconds/s.dt);targets=sorted(set(round(steps*v) for v in [.25,.5,.75,1.]));case=s.case
    for i in range(1,steps+1):
        start=time.perf_counter();s.advance();times.append((time.perf_counter()-start)*1000)
        if i not in targets:continue
        d,h,b=s.field();stem=f'{preset["key"]}-{model}-{i:04d}';spec=dict(effect=preset['key'],model=model,cells=case['cells'],extent=case['extent'],densityCap=s.c['densityCap'],material=preset['material'],time=s.t,source=case['source'],direction=s.B[0].tolist(),evidence='Reduced-order prescribed vortex flow, optional correlated scalar dispersion; not CFD or Rust')
        (out/(stem+'.json')).write_text(json.dumps(spec));d.astype('<f4').tofile(out/(stem+'.density.f32'));h.astype('<f4').tofile(out/(stem+'.temperature.f32'))
        if abs(b['particle_closure'])>max(1e-13,s.injected*1e-9) or abs(b['closure'])>max(1e-13,b['particle_mass']*1e-7):raise ArithmeticError('scalar mass budget failed')
        rows.append(dict(stem=stem,time=s.t,particles=len(s.mass),budget=b,**density_summary(d,cells=case['cells'],extent=case['extent'],cap=s.c['densityCap'],source=case['source'],direction=s.B[0].tolist())))
        print(stem,'markers',len(s.mass),'escaped',b['escaped']/max(s.injected,1e-30),'mass',b['grid_mass'],flush=True)
    return dict(key=preset['key'],model=model,steps=steps,dt=s.dt,markers_per_step=markers,timing=timing_summary(times),snapshots=rows)

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--seconds',type=float,default=4.);ap.add_argument('--markers',type=int,default=320);ap.add_argument('--models',nargs='+',choices=['base','rings','packets'],default=['base','rings','packets']);ap.add_argument('--effect',choices=[*CASES,'all'],default='all');ap.add_argument('--output',type=Path,default=ROOT/'reports/local/lab/lagrangian');a=ap.parse_args()
    if not .25<=a.seconds<=4 or not 32<=a.markers<=1024:ap.error('bounded experiment: .25..4 seconds and 32..1024 markers/step')
    set_num_threads(4);out=a.output;out.mkdir(parents=True,exist_ok=True);p=out/'experiment.json';rows=[];report=dict(status='RUNNING',scope=__doc__,implementation_sha256=sha256(Path(__file__)),rows=rows);atomic_report(p,report);catalog={x['key']:x for x in json.loads((ROOT/'effects/presets.json').read_text())['presets']}
    try:
        for key in CASES if a.effect=='all' else [a.effect]:
            for model in a.models:
                rows.append(run(catalog[key],model,a.seconds,out,a.markers));atomic_report(p,report)
        report['status']='PASS_EXECUTION_ONLY';atomic_report(p,report)
    except BaseException as e:report.update(status='FAIL',error=str(e));atomic_report(p,report);raise
if __name__=='__main__':main()
