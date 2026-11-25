#!/usr/bin/env python3
"""Independent CPU quadrature audit of source kernels. NOT Rust/WGSL execution.
Covers grid phase and orientation; excludes transport, obstacles, wall clipping.
"""
import itertools, json, math
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]

def kernel(points,pos,direction,dx,radius,length,new):
    q=points-np.asarray(pos); direction=np.asarray(direction,dtype=float);direction/=np.linalg.norm(direction)
    along=q@direction;radial=np.linalg.norm(q-along[:,None]*direction,axis=1)
    l=max(length if length>0 or not new else radius,dx);r=max(radius,dx*(1.1 if new else .65))
    def smooth(t):
        t=np.clip(t,0,1);return t*t*(3-2*t)
    w=(1-smooth(radial/r))*smooth((along+dx*.5)/dx)*smooth((l+dx*.5-along)/dx)
    if new:w*= (radius/r)**2*((length if length>0 else radius)/l)
    return w

def stats(x):
    return dict(min=float(min(x)),max=float(max(x)),mean=float(np.mean(x)),zero_samples=int(np.count_nonzero(np.asarray(x)==0)),cv=float(np.std(x)/np.mean(x)))

def main():
    presets=json.loads((ROOT/'effects/presets.json').read_text())['presets'];p=next(p for p in presets if p['key']=='cigarette_smoke');e=p['emitter'];rows=[]
    expected=.3*math.pi*e['radius']**2*e['length'] # radial smoothstep integral × axial length
    for quality,scale in [('low',.5),('medium',1),('high',2)]:
        dx=p['config']['cellSize']/scale;n=np.array(p['config']['cells'])*scale
        pts=(np.indices(tuple(n.astype(int))).reshape(3,-1).T+.5)*dx
        old_exact=kernel(pts,e['position'],e['direction'],dx,e['radius'],e['length'],False).sum()*dx**3
        new_exact=kernel(pts,e['position'],e['direction'],dx,e['radius'],e['length'],True).sum()*dx**3
        # Interior source only, sample phase throughout one cell and four directions.
        extent=math.ceil((e['length']+e['radius'])/dx)+4
        pts=np.array(list(itertools.product(np.arange(-extent,extent+1)+.5,repeat=3)))*dx
        vals=[[],[]]
        for direction in [(0,1,0),(1,1,1),(1,2,3),(1,0,1)]:
            for phase in itertools.product(np.arange(8)/8,repeat=3):
                for i,new in enumerate([False,True]):
                    vals[i].append(kernel(pts,np.array(phase)*dx,direction,dx,e['radius'],e['length'],new).sum()*dx**3/expected)
        row=dict(quality=quality,dx=dx,samples=len(vals[0]),old_exact_integral=float(old_exact),new_exact_integral=float(new_exact),analytic_integral=expected,old_ratio=stats(vals[0]),new_ratio=stats(vals[1]));rows.append(row)
        assert new_exact>0 and row['new_ratio']['zero_samples']==0
        assert .7<row['new_ratio']['mean']<1.3, row
        if quality!='high': assert old_exact<1e-18, row
    report={'status':'PASS','evidence':'independent NumPy cell-center quadrature of equations; NOT Rust/WGSL fluid runtime','rows':rows}
    path=ROOT/'reports/emitter-kernel-audit.json';path.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
