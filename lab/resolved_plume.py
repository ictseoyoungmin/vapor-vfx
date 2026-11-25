"""M2 local resolved plume experiment: SciPy MAC/DST, independent CPU only.
Same cropped grid, same conservative density source, three momentum/heat models.
No adaptive refinement, downstream artificial turbulence, or Rust evidence.
"""
from __future__ import annotations
import argparse,copy,json,time,math
from pathlib import Path
import numpy as np
from numba import njit,prange,set_num_threads
import bootstrap
from runtime_common import ROOT,sha256
from check_sdk import atomic_report
from quality_metrics import density_summary,timing_summary
from reference_fluid import Reference, project, sample, divergence
from reference_detail import trilerp,bounds
from coupled_density import source_distribution
from conservative_transport import transport

CASES={'cigarette_smoke':([36,72,36],.003,[.054,.03,.054]),'exhaled_aerosol':([64,32,32],.01,[.10,.16,.16])}
MODELS=('legacy_source','matched','seeded')

def local_preset(preset):
    p=copy.deepcopy(preset);cells,dx,pos=CASES[p['key']]
    p['config'].update(cells=cells.copy(),cellSize=dx,origin=[0,0,0],fixedDt=1/120,pressureIterations=256)
    p['emitter']['position']=pos.copy();return p

def smooth(x):
    t=np.clip(x,0.,1.);return t*t*(3.-2.*t)

def source_basis(p,e,dx,axis,direction):
    """Same physical support and midpoint quadrature as Rust plume.rs."""
    q=np.moveaxis(p,0,-1)[...,::-1].astype(np.float64)*dx-np.asarray(e['position']);r=e['radius'];l=e['length'] or r;taper=min(r*.5,l*.25)
    mask=np.linalg.norm(q-direction*l*.5,axis=-1)<=np.hypot(r,l*.5)+.87*dx
    a=q[mask];u=np.cross(direction,[0,1,0] if abs(direction[1])<.9 else [1,0,0]);u/=np.linalg.norm(u);v=np.cross(direction,u)
    ws=np.zeros(len(a));us=ws.copy();vs=ws.copy();count=0
    for x in [-.25,.25] if axis!=0 else [0]:
      for y in [-.25,.25] if axis!=1 else [0]:
       for z in [-.25,.25] if axis!=2 else [0]:
        b=a+dx*np.array([x,y,z]);h=b@direction;rad=b-h[:,None]*direction
        w=(1-smooth(np.linalg.norm(rad,axis=1)/r))*smooth(h/taper)*smooth((l-h)/taper)
        ws+=w;us+=w*(rad@u/r);vs+=w*(rad@v/r);count+=1
    result=[]
    for val in (ws/count,np.divide(us,ws,out=np.zeros_like(us),where=ws>0),np.divide(vs,ws,out=np.zeros_like(vs),where=ws>0)):
        arr=np.zeros(p.shape[1:],np.float32);arr[mask]=val;result.append(arr)
    return result

@njit(inline='always')
def mac_velocity(u,v,w,x,y,z):
    return trilerp(u,x,y-.5,z-.5),trilerp(v,x-.5,y,z-.5),trilerp(w,x-.5,y-.5,z)

@njit(inline='always')
def mac_trace(u,v,w,x,y,z,dt):
    a,b,c=mac_velocity(u,v,w,x,y,z);a,b,c=mac_velocity(u,v,w,x-.5*dt*a,y-.5*dt*b,z-.5*dt*c)
    return x-dt*a,y-dt*b,z-dt*c

@njit(inline='always')
def outside(x,y,z,nx,ny,nz):return x<0 or y<0 or z<0 or x>nx or y>ny or z>nz

@njit(parallel=True,cache=True)
def fast_advect(a,u,v,w,axis,dt):
    nz,ny,nx=a.shape;ox=0. if axis==0 else .5;oy=0. if axis==1 else .5;oz=0. if axis==2 else .5
    pred=np.empty_like(a);out=np.empty_like(a)
    for z in prange(nz):
      for y in range(ny):
       for x in range(nx):
        bx,by,bz=mac_trace(u,v,w,x+ox,y+oy,z+oz,dt)
        pred[z,y,x]=0. if axis==3 and outside(bx,by,bz,nx,ny,nz) else trilerp(a,bx-ox,by-oy,bz-oz)
    for z in prange(nz):
      for y in range(ny):
       for x in range(nx):
        px=x+ox;py=y+oy;pz=z+oz;bx,by,bz=mac_trace(u,v,w,px,py,pz,dt)
        if axis==3 and outside(bx,by,bz,nx,ny,nz):out[z,y,x]=0.;continue
        fx,fy,fz=mac_trace(u,v,w,px,py,pz,-dt)
        rev=0. if axis==3 and outside(fx,fy,fz,nx,ny,nz) else trilerp(pred,fx-ox,fy-oy,fz-oz)
        p=pred[z,y,x];q=p+.5*(a[z,y,x]-rev);lo,hi=bounds(a,bx-ox,by-oy,bz-oz)
        gain=min(1.,2/max(1.,math.sqrt((bx-px)**2+(by-py)**2+(bz-pz)**2)))
        r=p+gain*(min(hi,max(lo,q))-p);out[z,y,x]=max(0.,r) if axis==3 else r
    return out

class Resolved(Reference):
    def __init__(self,preset,model,*,domain=None):
        if model not in MODELS:raise ValueError('unknown variant')
        super().__init__(local_preset(preset) if domain is None else domain,'medium',False)
        self.model=model;self.amp=.05 if model=='seeded' else 0.;self.frequency=.2*self.e['speed']/(2*self.e['radius'])
        self.source,self.analytic=source_distribution(self.e,self.c);self.budgets=[]
        if model!='legacy_source':
            self.bases=[source_basis(p,self.e,self.dx,a,self.axis) for a,p in enumerate([*self.pv,self.p0])];self.w=[b[0] for b in self.bases]
        self.axis_length=float(self.e['length'] or self.e['radius'])
    def step(self):
        c=self.c;dt=self.dt;dx=self.dx;age=self.ticks*dt;active=not self.p or age<self.p['duration'];speed=self.e['speed'];rate=self.e['densityRate'];temp=self.e['temperature']
        if self.curve is not None and active:
            f=self.curve(age/self.p['duration']);speed*=f[0];rate*=np.clip(f[1],0,1)*max(0.,f[2])
        relax=20. if self.model=='legacy_source' else max(20.,2*speed/self.axis_length);phase=2*np.pi*self.frequency*age
        for a,v in enumerate(self.v):
            v+=(c['wind'][a]-v)*(1-np.exp(-c['drag']*dt))
            if a==1:v+=dt*(c['buoyancy']*sample(self.temp,self.pv[a],3)-c['densityWeight']*sample(self.rho,self.pv[a],3))
            if active:
                m=1. if self.amp==0 else 1+self.amp*(self.bases[a][1]*np.cos(phase)+self.bases[a][2]*np.sin(phase))
                v+=(self.axis[a]*speed*m-v)*(1-np.exp(-relax*self.w[a]*dt))
        u=(self.v[0][...,:-1]+self.v[0][...,1:])*.5;v=(self.v[1][:,:-1,:]+self.v[1][:,1:,:])*.5;w=(self.v[2][:-1,...]+self.v[2][1:,...])*.5
        curl=np.stack((np.gradient(w,dx,axis=1)-np.gradient(v,dx,axis=0),np.gradient(u,dx,axis=0)-np.gradient(w,dx,axis=2),np.gradient(v,dx,axis=2)-np.gradient(u,dx,axis=1)),axis=-1)
        mag=np.linalg.norm(curl,axis=-1);gz,gy,gx=np.gradient(mag,dx);g=np.stack((gx,gy,gz),axis=-1);force=np.cross(g/(np.linalg.norm(g,axis=-1,keepdims=True)+1e-6),curl)*c['vorticity']*dx
        force[[0,-1],:,:,:]=0;force[:,[0,-1],:,:]=0;force[:,:,[0,-1],:]=0
        for a,v in enumerate(self.v):
            f=np.moveaxis(force[...,a],2-a,0);vv=np.moveaxis(v,2-a,0);vv[1:-1]+=.5*dt*(f[:-1]+f[1:]);self.clamps+=int(np.count_nonzero(np.abs(v)>c['maxVelocity']));np.clip(v,-c['maxVelocity'],c['maxVelocity'],out=v)
        self.v=[fast_advect(v,*self.v,a,dt/dx) for a,v in enumerate(self.v)]
        before,after=project(self.v,dx,self.eigen)
        for v in self.v:self.clamps+=int(np.count_nonzero(np.abs(v)>c['maxVelocity']));np.clip(v,-c['maxVelocity'],c['maxVelocity'],out=v)
        after=float(np.sqrt(np.mean(divergence(self.v,dx).astype(np.float64)**2)))
        mass0=float(self.rho.sum(dtype=np.float64)*dx**3);q,out,sub=transport(self.rho,self.v,dx,dt)
        q1=q*np.exp(-c['densityDecay']*dt);dec=float((q-q1).sum()*dx**3);inc=self.source*rate*dt if active else 0.;injected=float(np.sum(inc)*dx**3);q2=q1+inc
        rho=np.minimum(q2,c['densityCap']);sat=float((q2-rho).sum()*dx**3);self.rho=rho.astype(np.float32);mass1=float(self.rho.sum(dtype=np.float64)*dx**3)
        self.budgets.append(dict(injected=injected,outflow=out,decayed=dec,saturated=sat,after=mass1,residual=mass1-(mass0+injected-out-dec-sat),substeps=sub))
        self.temp=fast_advect(self.temp,*self.v,3,dt/dx)*np.exp(-c['cooling']*dt)
        if active:self.temp+=np.maximum(temp-self.temp,0)*(1-np.exp(-relax*self.w[3]*dt))
        self.ticks+=1;return before,after
    def flow_metrics(self):
        u=(self.v[0][...,:-1]+self.v[0][...,1:])*.5;v=(self.v[1][:,:-1,:]+self.v[1][:,1:,:])*.5;w=(self.v[2][:-1]+self.v[2][1:])*.5
        curl=np.stack((np.gradient(w,self.dx,axis=1)-np.gradient(v,self.dx,axis=0),np.gradient(u,self.dx,axis=0)-np.gradient(w,self.dx,axis=2),np.gradient(v,self.dx,axis=2)-np.gradient(u,self.dx,axis=1)),axis=-1)
        mag=np.linalg.norm(curl,axis=-1);xyz=np.moveaxis(self.p0,0,-1)[...,::-1]*self.dx-np.asarray(self.e['position']);h=xyz@self.axis;rad=np.linalg.norm(xyz-h[...,None]*self.axis,axis=-1)
        mask=(h>self.axis_length)&(rad<2*self.e['radius']);axial=u*self.axis[0]+v*self.axis[1]+w*self.axis[2];cross2=np.maximum(0,u*u+v*v+w*w-axial*axial)
        return dict(max_speed=float(np.sqrt(u*u+v*v+w*w).max()),vorticity_rms_downstream=float(np.sqrt(np.mean(mag[mask]**2))),crossflow_rms_downstream=float(np.sqrt(np.mean(cross2[mask]))),kinetic_energy_integral=float(.5*np.sum(u*u+v*v+w*w,dtype=np.float64)*self.dx**3))

def run(preset,model,seconds,out,*,domain=None):
    s=Resolved(preset,model,domain=domain);c=s.c;e=s.e;extent=[n*s.dx for n in c['cells']];steps=round(seconds/s.dt);sample_ticks=sorted(set(max(1,round(t*steps)) for t in [.125,.375,.625,1]));rows=[];times=[];maxdiv=0.
    small=np.zeros((4,4,4),np.float32);u=np.zeros((4,4,5),np.float32);v=np.zeros((4,5,4),np.float32);w=np.zeros((5,4,4),np.float32);fast_advect(small,u,v,w,3,.1)
    for i in range(1,steps+1):
        start=time.perf_counter();_,div=s.step();times.append((time.perf_counter()-start)*1000);maxdiv=max(div,maxdiv)
        if i not in sample_ticks:continue
        if not all(np.isfinite(a).all() for a in [s.rho,s.temp,*s.v]):raise ArithmeticError('nonfinite field')
        stem=f'{preset["key"]}-{model}-{i:04d}'
        spec=dict(effect=preset['key'],model=model,cells=c['cells'],extent=extent,densityCap=c['densityCap'],material=preset['material'],time=i*s.dt,source=e['position'],direction=s.axis.tolist(),evidence='Independent CPU MAC/DST uniform grid, not Rust/GPU')
        (out/(stem+'.json')).write_text(json.dumps(spec));s.rho.astype('<f4').tofile(out/(stem+'.density.f32'));s.temp.astype('<f4').tofile(out/(stem+'.temperature.f32'))
        rows.append(dict(stem=stem,time=i*s.dt,**density_summary(s.rho,cells=c['cells'],extent=extent,cap=c['densityCap'],source=e['position'],direction=s.axis),flow=s.flow_metrics()))
        print(preset['key'],model,'t=',round(i*s.dt,3),'density=',rows[-1]['density_integral'],'vorticity=',rows[-1]['flow']['vorticity_rms_downstream'],flush=True)
    b=s.budgets;inj=sum(q['injected'] for q in b);outflow=sum(q['outflow'] for q in b);dec=sum(q['decayed'] for q in b);sat=sum(q['saturated'] for q in b);residual=b[-1]['after']-(inj-outflow-dec-sat)
    if not inj>0 or abs(residual)>max(1e-13,inj*1e-6):raise ArithmeticError('density budget failed')
    return dict(key=preset['key'],model=model,cells=c['cells'],extent=extent,diameter_cells=2*e['radius']/s.dx,steps=steps,dt=s.dt,source_integral=s.analytic,seed_amplitude=s.amp,seed_frequency_hz=s.frequency,clamps=s.clamps,max_divergence_after=maxdiv,timing=timing_summary(times),mass_budget=dict(injected=inj,boundary_outflow=outflow,decayed=dec,saturated=sat,final=b[-1]['after'],relative_residual=residual/inj,outflow_fraction=outflow/inj),snapshots=rows)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--seconds',type=float,default=4);p.add_argument('--threads',type=int,default=2);p.add_argument('--effect',choices=CASES,required=True);p.add_argument('--models',nargs='+',choices=MODELS,default=list(MODELS));p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if not .25<=a.seconds<=4 or not 1<=a.threads<=4:p.error('seconds .25..4; threads 1..4')
    set_num_threads(a.threads);out=a.output;out.mkdir(parents=True,exist_ok=True);path=out/'experiment.json';rows=[]
    catalog={p['key']:p for p in json.loads((ROOT/'effects/presets.json').read_text())['presets']};report=dict(status='RUNNING',evidence=__doc__,implementation_sha256=sha256(Path(__file__)),rows=rows);atomic_report(path,report)
    try:
      for m in a.models:
        rows.append(run(catalog[a.effect],m,a.seconds,out));atomic_report(path,report)
      report['status']='PASS_EXECUTION_ONLY';atomic_report(path,report)
    except BaseException as e:report.update(status='FAIL',error=str(e));atomic_report(path,report);raise
if __name__=='__main__':main()
