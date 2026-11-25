"""Independent SciPy MAC experiment: cell/face averaged physical source.
Compares legacy grid-broadened and fixed physical kernels; not a Rust runtime.
"""
from __future__ import annotations
import argparse,json,time,copy,math
from pathlib import Path
import numpy as np
import bootstrap  # enables explicit shared validation helpers
from reference_fluid import Reference
from quality_metrics import density_summary,timing_summary
from runtime_common import ROOT,sha256

def smooth(x):
    t=np.clip(x,0.,1.);return t*t*(3.-2.*t)

def physical_weights(p,e,dx,direction,axis,samples=6):
    """Cell volume or MAC face average. Axis=3 denotes scalar cell."""
    if samples not in (2,4,6,8):raise ValueError('quadrature samples must be 2/4/6/8')
    r=float(e['radius']);length=float(e['length'] or r);taper=min(r*.5,length*.25)
    q=np.moveaxis(p,0,-1)[...,::-1].astype(np.float64)*dx-np.asarray(e['position'])
    support=np.linalg.norm(q-direction*length*.5,axis=-1)<=np.hypot(r,length*.5)+np.sqrt(3)*dx*.5
    a=q[support];out=np.zeros(p.shape[1:],np.float32)
    if not len(a):return out
    offsets=(np.arange(samples)+.5)/samples-.5
    axes=[offsets if axis!=i else np.array([0.]) for i in range(3)]
    weight=np.zeros(len(a),np.float64)
    for oz in axes[2]:
      for oy in axes[1]:
       for ox in axes[0]:
        v=a+dx*np.array([ox,oy,oz]);ax=v@direction
        rad=np.sqrt(np.maximum(0.,np.einsum('ij,ij->i',v,v)-ax*ax))
        weight+=(1-smooth(rad/r))*smooth(ax/taper)*smooth((length-ax)/taper)
    out[support]=(weight/(len(axes[0])*len(axes[1])*len(axes[2]))).astype(np.float32)
    return out

def physical_integral(e):
    r=e['radius'];l=e['length'] or r;taper=min(r*.5,l*.25)
    return .3*np.pi*r*r*(l-taper)

def make_reference(preset,scale,mode,samples,duration):
    p=copy.deepcopy(preset);p['config']['cells']=[n*scale for n in p['config']['cells']];p['config']['cellSize']/=scale
    dt=min(p['config']['fixedDt'], .8*p['config']['cellSize']/max(.15,p['emitter']['speed']))
    n=max(2,math.ceil(duration/dt));p['config']['fixedDt']=duration/n
    s=Reference(p,'medium',False)
    if mode=='physical':
        s.w=[physical_weights(q,s.e,s.dx,s.axis,a,samples) for a,q in enumerate([*s.pv,s.p0])]
        mass=float(s.w[3].sum(dtype=np.float64))*s.dx**3
        if mass<=0:raise RuntimeError('quadrature misses emitter')
        s.scale=physical_integral(s.e)/mass
    return s,n

def run(preset,scale,mode,samples,duration,output):
    s,n=make_reference(preset,scale,mode,samples,duration);c=s.c;e=s.e;extent=[v*s.dx for v in c['cells']]
    times=[];res=[];snapshots=[];steps=sorted(set([max(1,n//2),n]));source_integral=float(s.w[3].sum(dtype=np.float64))*s.dx**3*s.scale
    for k in range(1,n+1):
        start=time.perf_counter();before,after=s.step();times.append((time.perf_counter()-start)*1000);res.append([before,after])
        if k in steps:
            if not all(np.isfinite(x).all() for x in [s.rho,s.temp,*s.v]):raise RuntimeError('invalid reference state')
            stem=f'{preset["key"]}-{scale}x-{mode}-{k:04d}'
            spec=dict(effect=preset['key'],model=mode,cells=c['cells'],extent=extent,densityCap=c['densityCap'],material=preset['material'],time=k*s.dt,source=e['position'],direction=s.axis.tolist(),evidence='Independent SciPy MAC CPU experiment; no Rust/GPU execution')
            (output/(stem+'.json')).write_text(json.dumps(spec));s.rho.astype('<f4').tofile(output/(stem+'.density.f32'));s.temp.astype('<f4').tofile(output/(stem+'.temperature.f32'))
            snapshots.append(dict(stem=stem,time=k*s.dt,**density_summary(s.rho,cells=c['cells'],extent=extent,cap=c['densityCap'],source=e['position'],direction=s.axis)))
    return dict(key=preset['key'],scale=scale,mode=mode,cells=c['cells'],dt=s.dt,steps=n,source_integral=source_integral,analytic_integral=physical_integral(e),source_cells=int(np.count_nonzero(s.w[3])),diameter_cells=2*e['radius']/s.dx,max_divergence_after=max(x[1] for x in res),clamps=s.clamps,timing=timing_summary(times),snapshots=snapshots)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--scales',nargs='+',type=int,choices=[1,2,3,4],default=[1,3]);p.add_argument('--duration',type=float,default=.35);p.add_argument('--samples',type=int,choices=[2,4,6,8],default=6);p.add_argument('--output',type=Path,default=ROOT/'reports/local/lab/source');a=p.parse_args()
    if not 0<a.duration<=2:p.error('duration must be 0..2 s')
    a.output.mkdir(parents=True,exist_ok=True);report=a.output/'experiment.json';rows=[]
    presets={p['key']:p for p in json.loads((ROOT/'effects/presets.json').read_text())['presets']}
    try:
      for key in ['cigarette_smoke','exhaled_aerosol']:
       for scale in a.scales:
        for mode in ['legacy','physical']:
          row=run(presets[key],scale,mode,a.samples,a.duration,a.output);rows.append(row);report.write_text(json.dumps(dict(status='RUNNING',evidence=__doc__,rows=rows),indent=2));print(key,scale,mode,row['source_integral'],row['snapshots'][-1]['plume'],flush=True)
      report.write_text(json.dumps(dict(status='PASS',evidence=__doc__,samples=a.samples,implementation_sha256=sha256(Path(__file__)),rows=rows),indent=2))
    except BaseException as e:
      report.write_text(json.dumps(dict(status='FAIL',error=str(e),rows=rows),indent=2));raise
if __name__=='__main__':main()
