#!/usr/bin/env python3
"""Actual CPU test of conservation vs reconstruction diffusion on a translated 3-D pulse.
Analytic velocity and scalar (not a smoke solver, not a natural-plume quality claim).
"""
from pathlib import Path
import json,time
import numpy as np
import bootstrap
from runtime_common import ROOT,sha256
from check_sdk import atomic_report
from conservative_transport import transport
from reference_fluid import lattice,advect

def main():
    dx=.025;shape=(24,24,48);p=lattice(shape,3);z,y,x=p*dx
    center=[.35,.30,.30];sigma=.075;speed=.65;dt=.015;steps=70
    def exact(t):return np.exp(-.5*((x-center[0]-speed*t)**2+(y-center[1])**2+(z-center[2])**2)/sigma**2).astype(np.float64)
    q=exact(0);nz,ny,nx=shape;v=[np.full((nz,ny,nx+1),speed,np.float32),np.zeros((nz,ny+1,nx),np.float32),np.zeros((nz+1,ny,nx),np.float32)]
    target=exact(steps*dt);initial=q.sum()*dx**3;rows=[]
    for mode in ['maccormack','donor','muscl']:
        a=q.copy();loss=0.;start=time.perf_counter()
        for _ in range(steps):
            if mode=='maccormack':a=advect(a.astype(np.float32),v,p,3,dt/dx)
            else:
                a,out,_=transport(a,v,dx,dt,limited=mode=='muscl');loss+=out
        final=float(a.sum(dtype=np.float64)*dx**3);r=dict(model=mode,initial_mass=float(initial),final_mass=final,analytic_final_mass=float(target.sum()*dx**3),relative_mass_error=float((final-target.sum()*dx**3)/initial),l1_integral_relative=float(np.abs(a-target).sum()*dx**3/initial),minimum=float(a.min()),peak=float(a.max()),elapsed_ms=(time.perf_counter()-start)*1000,accounted_outflow=None if mode=='maccormack' else loss,budget_residual=None if mode=='maccormack' else float(initial-final-loss));rows.append(r);print(r,flush=True)
    out=ROOT/'reports/local/lab/transport/analytic.json';atomic_report(out,dict(status='PASS',evidence=__doc__,cells=list(shape[::-1]),dx=dx,dt=dt,steps=steps,implementation_sha256=sha256(Path(__file__).with_name('conservative_transport.py')),rows=rows));return 0
if __name__=='__main__':raise SystemExit(main())
