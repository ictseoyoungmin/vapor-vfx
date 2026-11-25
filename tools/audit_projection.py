#!/usr/bin/env python3
"""Independent CPU numerical audit of the open-boundary pressure stencil.

Runs NumPy equations, NOT the Rust solver, FFI, WGSL, or a game engine.
The paired Rust unit test exercises the actual solver when rustc is available.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]

def audit() -> dict:
    nx,ny,nz=6,8,6;dx=.1
    velocity=np.zeros((nz+1,ny+1,nx+1,3),dtype=np.float64)
    velocity[2:4,2:5,2:4,1]=.3
    def divergence(v):
        return ((v[:nz,:ny,1:nx+1,0]-v[:nz,:ny,:nx,0])+
                (v[:nz,1:ny+1,:nx,1]-v[:nz,:ny,:nx,1])+
                (v[1:nz+1,:ny,:nx,2]-v[:nz,:ny,:nx,2]))/dx
    rhs=divergence(velocity)
    p=np.zeros((nz+2,ny+2,nx+2),dtype=np.float64)
    zz,yy,xx=np.indices((nz,ny,nx));parity=(xx+yy+zz)%2
    def neighbors():
        return (p[1:-1,1:-1,:-2]+p[1:-1,1:-1,2:]+p[1:-1,:-2,1:-1]+
                p[1:-1,2:,1:-1]+p[:-2,1:-1,1:-1]+p[2:,1:-1,1:-1])
    for _ in range(256):
        for color in (0,1):
            center=p[1:-1,1:-1,1:-1]
            candidate=(neighbors()-rhs*dx*dx)/6
            mask=parity==color
            center[mask]+=1.7*(candidate[mask]-center[mask])
    residual=(neighbors()-6*p[1:-1,1:-1,1:-1])/(dx*dx)-rhs
    projected=velocity.copy()
    projected[:nz,:ny,:nx+1,0]-=(p[1:-1,1:-1,1:]-p[1:-1,1:-1,:-1])/dx
    projected[:nz,:ny+1,:nx,1]-=(p[1:-1,1:,1:-1]-p[1:-1,:-1,1:-1])/dx
    projected[:nz+1,:ny,:nx,2]-=(p[1:,1:-1,1:-1]-p[:-1,1:-1,1:-1])/dx
    legacy=projected.copy()
    for component,axis in [(0,2),(1,1),(2,0)]:
        lo=[slice(None)]*4;hi=lo.copy();lo[3]=hi[3]=component;lo[axis]=0;hi[axis]=(nx,ny,nz)[component]
        legacy[tuple(lo)]=np.minimum(legacy[tuple(lo)],0)
        legacy[tuple(hi)]=np.maximum(legacy[tuple(hi)],0)
    rms=lambda v:float(np.sqrt(np.mean(v*v)))
    result={
        'schema':'vapor.projection-math-audit/1',
        'evidence':'independent NumPy CPU stencil reproduction; NOT Rust/WGSL runtime validation',
        'grid':[nx,ny,nz],'iterations':256,'cell_size':dx,
        'initial_divergence_rms':rms(rhs),'pressure_residual_rms':rms(residual),
        'old_post_clip_divergence_rms':rms(divergence(legacy)),
        'preserved_open_flux_divergence_rms':rms(divergence(projected)),
        'sources':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest()
                   for f in [ROOT/'crates/vapor-core/src/solver.rs',ROOT/'shaders/compute/mac.wgsl']},
    }
    assert result['old_post_clip_divergence_rms']>1e-3
    assert result['preserved_open_flux_divergence_rms']<1e-10
    assert np.max(np.abs(divergence(projected)+residual))<1e-12
    result['status']='PASS'
    return result

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,default=ROOT/'reports/projection-math-audit.json')
    args=ap.parse_args();result=audit();args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
