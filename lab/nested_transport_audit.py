"""Actual scalar pulse crossing a fine/coarse interface under prescribed translation."""
import json,time
from pathlib import Path
import numpy as np
from nested_transport import advance,constant_velocity
from conservative_transport import transport
ROOT=Path(__file__).resolve().parents[1]
def blob(x,y,z,shift):return np.exp(-((x-.32-shift)**2/(2*.095**2)+(y-.4)**2/(2*.105**2)+(z-.4)**2/(2*.105**2)))
def grid(n,dx,origin):
    z,y,x=np.indices(n,dtype=np.float64);return origin+(x+.5)*dx,(y+.5)*dx,(z+.5)*dx
# 0.8m near + 1.6m far, 0.8m square section; 4:1 ratio.
fshape=(32,32,32);cshape=(8,8,16);dx=.025;r=4;dx2=dx*r;u=.5;duration=2.8;dt=.025;steps=round(duration/dt)
f=blob(*grid(fshape,dx,0),0);c=blob(*grid(cshape,dx2,.8),0);vf=constant_velocity(fshape,u);vc=constant_velocity(cshape,u);m=f.sum()*dx**3+c.sum()*dx2**3
start=time.perf_counter();outer=interface=0.;rows=[]
for i in range(steps):
    f,c,q=advance(f,c,vf,vc,dx,r,dt);outer+=q['outer_outflow'];interface+=q['interface_transfer']
    if i in (0,31,63,95,steps-1):rows.append(dict(time=(i+1)*dt,fine_mass=float(f.sum()*dx**3),coarse_mass=float(c.sum()*dx2**3),outer_outflow=outer,interface_transfer=interface))
seconds=time.perf_counter()-start;final=f.sum()*dx**3+c.sum()*dx2**3;expected=blob(*grid(fshape,dx,0),u*duration);ec=blob(*grid(cshape,dx2,.8),u*duration);error=(abs(f-expected).sum()*dx**3+abs(c-ec).sum()*dx2**3)/m
# uniform fine reference for same prescribed advection (not CFD); report cell cost and closure, not visual success.
n=(32,32,96);v=constant_velocity(n,u);full=blob(*grid(n,dx,0),0);fm=full.sum()*dx**3;loss=0.;start=time.perf_counter()
for _ in range(steps):full,l,_=transport(full,v,dx,dt);loss+=l
full_seconds=time.perf_counter()-start;full_error=abs(full-blob(*grid(n,dx,0),u*duration)).sum()*dx**3/fm
report=dict(schema='vapor.research-nested-scalar/1',status='PASS_SCALAR_INTERFACE_ONLY',notice='Prescribed velocity, fixed two slabs, no pressure or momentum coupling; not Rust or plume visual evidence',fine_shape=list(fshape),coarse_shape=list(cshape),uniform_shape=list(n),duration=duration,steps=steps,initial_mass=float(m),final_mass=float(final),outer_outflow=outer,interface_transfer=interface,relative_closure=float((final+outer-m)/m),normalized_l1=float(error),uniform_normalized_l1=float(full_error),cells=int(f.size+c.size),uniform_cells=int(full.size),seconds=seconds,uniform_seconds=full_seconds,rows=rows)
if abs(report['relative_closure'])>1e-10 or interface<=0 or min(f.min(),c.min())<0:raise SystemExit('interface gate failed')
path=ROOT/'reports/research-nested-scalar.json';path.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
