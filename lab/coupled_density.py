"""M2 coupled plume experiment; independent SciPy MAC/DST, not Rust.
Compare legacy density against MUSCL alone and MUSCL + source-space quadrature.
The momentum/heat model, spectral projection and optics are held constant.
"""
import argparse, json, time
from pathlib import Path
import numpy as np
import bootstrap
from reference_fluid import Reference,advect
from conservative_transport import transport
from runtime_common import ROOT,sha256
from quality_metrics import density_summary,timing_summary
from check_sdk import atomic_report

def source_distribution(e,cfg):
    """12×12×24 source-space quadrature; density increment per unit rate × second."""
    n=np.array(cfg['cells']);dx=float(cfg['cellSize']);o=np.array(cfg['origin'],float)
    p=np.array(e['position'],float);d=np.array(e['direction'],float);d/=np.linalg.norm(d)
    r=float(e['radius']);l=float(e['length'] or r);taper=min(r*.5,l*.25)
    width=r*np.sqrt(np.maximum(0.,1-d*d));end=p+d*l
    if np.any(np.minimum(p,end)-width<o) or np.any(np.maximum(p,end)+width>o+n*dx):raise ValueError('clipped source')
    u=np.cross(d,[0,1,0] if abs(d[1])<.9 else [1,0,0]);u/=np.linalg.norm(u);v=np.cross(d,u)
    def smooth(x):t=np.clip(x,0,1);return t*t*(3-2*t)
    h,s,phi=np.meshgrid((np.arange(12)+.5)*l/12,(np.arange(12)+.5)/12,(np.arange(24)+.5)*2*np.pi/24,indexing='ij')
    h,s,phi=[x.ravel() for x in [h,s,phi]]
    w=s*(1-smooth(s))*smooth(h/taper)*smooth((l-h)/taper)
    q=p+h[:,None]*d+r*s[:,None]*(np.cos(phi)[:,None]*u+np.sin(phi)[:,None]*v)
    i=np.clip(np.floor((q-o)/dx).astype(np.int64),0,n-1)
    mass=.3*np.pi*r*r*(l-taper);field=np.zeros(tuple(n[::-1]),np.float64)
    np.add.at(field,(i[:,2],i[:,1],i[:,0]),w*mass/(w.sum()*dx**3))
    return field,mass

class Coupled(Reference):
    def __init__(self,preset,quality,model):
        super().__init__(preset,quality,False);self.model=model;self.budgets=[]
        if model=='physical':self.source,self.analytic=source_distribution(self.e,self.c)
        else:self.source=self.w[3].astype(np.float64)*self.scale;self.analytic=None
    def advance_scalars(self,active,rate,temp):
        dt=self.dt;dv=self.dx**3;rho=self.rho
        before=float(rho.sum(dtype=np.float64)*dv)
        if self.model=='legacy':
            q=advect(rho,self.v,self.p0,3,dt/self.dx).astype(np.float64);out=None;n=0
        else:q,out,n=transport(rho,self.v,self.dx,dt)
        transported=float(q.sum()*dv);decayed_q=q*np.exp(-self.c['densityDecay']*dt);decayed=float((q-decayed_q).sum()*dv)
        inc=self.source*rate*dt if active else 0.;new=decayed_q+inc;injected=float(np.sum(inc)*dv)
        clamped=np.minimum(new,self.c['densityCap']);saturated=float((new-clamped).sum()*dv);self.rho=clamped.astype(np.float32)
        after=float(self.rho.sum(dtype=np.float64)*dv)
        self.temp=advect(self.temp,self.v,self.p0,3,dt/self.dx)*np.exp(-self.c['cooling']*dt)
        if active:self.temp+=np.maximum(temp-self.temp,0)*(1-np.exp(-20*self.w[3]*dt))
        residual=None if out is None else after-(before+injected-out-decayed-saturated)
        self.budgets.append(dict(before=before,after=after,injected=injected,outflow=out,decayed=decayed,saturated=saturated,residual=residual,transport_delta=transported-before,substeps=n))

def run(preset,quality,model,seconds,out):
    sim=Coupled(preset,quality,model);c=sim.c;e=sim.e;steps=round(seconds/sim.dt);samples=sorted(set([max(1,steps//3),max(1,2*steps//3),steps]));rows=[];times=[];maxdiv=0.;extent=[n*sim.dx for n in c['cells']]
    for i in range(1,steps+1):
        start=time.perf_counter();_,div=sim.step();times.append((time.perf_counter()-start)*1000);maxdiv=max(maxdiv,div)
        if i not in samples:continue
        stem=f'{preset["key"]}-{quality}-{model}-{i:04d}'
        spec=dict(effect=preset['key'],model=model,cells=c['cells'],extent=extent,densityCap=c['densityCap'],material=preset['material'],time=i*sim.dt,source=e['position'],direction=sim.axis.tolist(),evidence='Actual independent SciPy MAC/DST + CPU density research; not Rust')
        (out/(stem+'.json')).write_text(json.dumps(spec));sim.rho.astype('<f4').tofile(out/(stem+'.density.f32'));sim.temp.astype('<f4').tofile(out/(stem+'.temperature.f32'))
        rows.append(dict(stem=stem,time=i*sim.dt,**density_summary(sim.rho,cells=c['cells'],extent=extent,cap=c['densityCap'],source=e['position'],direction=sim.axis)))
    budget=sim.budgets;injected=sum(b['injected'] for b in budget);decayed=sum(b['decayed'] for b in budget);saturated=sum(b['saturated'] for b in budget);outflow=None if model=='legacy' else sum(b['outflow'] for b in budget);residual=None if outflow is None else budget[-1]['after']-(injected-outflow-decayed-saturated)
    if residual is not None and abs(residual)>max(1e-13,injected*1e-6):raise ArithmeticError('density budget failed')
    result=dict(key=preset['key'],quality=quality,model=model,cells=c['cells'],steps=steps,dt=sim.dt,source_volume=float(sim.source.sum()*sim.dx**3),analytic_source_volume=sim.analytic,clamps=sim.clamps,max_divergence_after=maxdiv,timing=timing_summary(times),mass_budget=dict(injected=injected,decayed=decayed,saturated=saturated,boundary_outflow=outflow,final=budget[-1]['after'],closure_residual=residual,relative_residual=None if residual is None else residual/max(injected,1e-30),transport_delta=sum(b['transport_delta'] for b in budget),max_substeps=max(b['substeps'] for b in budget)),snapshots=rows)
    print(preset['key'],model,'integral',budget[-1]['after'],'budget residual',residual,flush=True);return result

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--quality',choices=['low','medium','high'],default='medium');ap.add_argument('--seconds',type=float,default=1.5);ap.add_argument('--output',type=Path,default=ROOT/'reports/local/lab/coupled-density');a=ap.parse_args()
    if not .1<=a.seconds<=4:ap.error('seconds must be .1..4')
    out=a.output;out.mkdir(parents=True,exist_ok=True);path=out/'experiment.json';rows=[]
    catalog={p['key']:p for p in json.loads((ROOT/'effects/presets.json').read_text())['presets']}
    report=dict(status='RUNNING',evidence=__doc__,implementation_sha256=sha256(Path(__file__)),rows=rows);atomic_report(path,report)
    try:
        for key in ['cigarette_smoke','exhaled_aerosol']:
            for model in ['legacy','muscl','physical']:
                rows.append(run(catalog[key],a.quality,model,a.seconds,out));atomic_report(path,report)
        report['status']='PASS';atomic_report(path,report)
    except BaseException as exc:report.update(status='FAIL',error=str(exc));atomic_report(path,report);raise
if __name__=='__main__':main()
