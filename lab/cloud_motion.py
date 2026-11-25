"""Conservative animation of a baked cloud in local coordinates.
Prescribed, discretely divergence-free curl on MAC faces; not weather dynamics.
Transport is performed on the actual density field, never on rendered images.
"""
from __future__ import annotations
import argparse, json, math, sys, time
from array import array
from pathlib import Path
import numpy as np
import bootstrap
from runtime_common import ROOT
from check_sdk import atomic_report
from conservative_transport import transport
sys.path.insert(0,str(ROOT/'bindings/python'))
from vapor_game.field_asset import BakedField, read_field_asset, encode_field_asset


def curl_velocity(cells, extent, t, speed=2.):
    nx,ny,nz=cells; ex,ey,ez=extent
    dx=ex/nx
    if not np.allclose(np.array(extent)/cells,dx,rtol=1e-12):raise ValueError('isotropic MAC grid required')
    if not np.isfinite(t) or not 0<=speed<=20:raise ValueError('invalid wind')
    def pot(axis):
        n=(nz,ny,nx);i=2-axis
        # A components live on edges parallel to their axis.
        coords=[(np.arange(k)+.5)/k if j==i else np.linspace(0,1,k+1) for j,k in enumerate(n)]
        z,y,x=np.meshgrid(*coords,indexing='ij',sparse=True)
        def win(c):return np.where((c==0)|(c==1),0.,np.sin(np.pi*c)**2)
        phase=.27*t+axis*2.1
        # Two length scales with continuous phase evolution and boundary taper.
        return dx*min(cells)*win(x)*win(y)*win(z)*(np.sin(2*np.pi*(x+0.6*y-.8*z)+phase)+.37*np.sin(2*np.pi*(2.1*x-1.6*y+1.3*z)-.63*phase))
    ax,ay,az=[pot(i) for i in range(3)]
    u=(np.diff(az,axis=1)-np.diff(ay,axis=0))/dx
    v=(np.diff(ax,axis=0)-np.diff(az,axis=2))/dx
    w=(np.diff(ay,axis=2)-np.diff(ax,axis=1))/dx
    m=max(np.max(np.abs(a)) for a in (u,v,w));f=speed/max(m,1e-30)
    return [a*f for a in (u,v,w)]

def run(source, out, seconds=12., fps=2., speed=2.):
    from vapor_game.field_sequence import encode_index, frame_filename
    field=read_field_asset(source);cells=field.cells;ext=field.extent;dx=ext[0]/cells[0];dv=dx**3
    if not np.allclose(np.array(ext)/cells,dx):raise ValueError('isotropic grid required')
    if not 1<=fps<=12 or not 0<seconds<=120 or abs(seconds*fps-round(seconds*fps))>1e-8:raise ValueError('invalid schedule')
    rho=np.array(field.density,dtype=np.float64).reshape(cells[::-1]);temp=np.array(field.temperature,dtype=np.float64).reshape(cells[::-1]);initial=rho.copy();m0=rho.sum()*dv
    if m0<=0:raise ValueError('empty input')
    out.mkdir(parents=True,exist_ok=True);rows=[];loss=0.;temp_loss=0.;start=time.perf_counter()
    for i in range(round(seconds*fps)+1):
        t=i/fps
        if i:
            v=curl_velocity(cells,ext,t-.5/fps,speed)
            div=(np.diff(v[0],axis=2)+np.diff(v[1],axis=1)+np.diff(v[2],axis=0))/dx
            rho,removed,sub=transport(rho,v,dx,1/fps);loss+=removed
            if np.any(temp):temp,removed,_=transport(temp,v,dx,1/fps);temp_loss+=removed
            maxdiv=float(np.abs(div).max())
        else:sub=0;maxdiv=0.
        if rho.min()< -1e-12 or rho.max()>field.density_cap*(1+1e-6):raise ArithmeticError('transport scalar bounds')
        # -0 and tiny signed roundoff can be removed only below 1e-12; no global renormalization.
        r=np.maximum(rho,0).astype(np.float32);h=np.maximum(temp,0).astype(np.float32)
        f=BakedField(cells,ext,field.density_cap,field.time+t,array('f',r.ravel()),array('f',h.ravel()))
        raw=encode_field_asset(f);(out/frame_filename(i)).write_bytes(raw)
        row=dict(index=i,time=field.time+t,relative_mass_error=float((r.sum(dtype=np.float64)*dv+loss-m0)/m0),mass=float(r.sum(dtype=np.float64)*dv),boundary_loss=loss,divergence_max=maxdiv,substeps=sub,relative_shape_change=float(np.abs(r-initial).sum()/initial.sum()),peak_density=float(r.max()))
        rows.append(row);print('cloud',i,t,row['relative_mass_error'],row['relative_shape_change'],flush=True)
    # Index construction reads one frame at a time, not the complete sequence.
    from vapor_game.field_sequence import index_from_paths
    (out/'sequence.vpa').write_bytes(index_from_paths(out/frame_filename(i) for i in range(len(rows))))
    report=dict(status='PASS' if max(abs(r['relative_mass_error']) for r in rows)<1e-6 else 'FAIL',model=__doc__,cells=cells,extent=ext,seconds=seconds,keyframe_fps=fps,speed=speed,elapsed_seconds=time.perf_counter()-start,rows=rows,initial_mass=float(m0),boundary_loss=loss)
    atomic_report(out/'motion.json',report)
    if report['status']!='PASS':raise ArithmeticError('cloud budget failed')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('output',type=Path);p.add_argument('--seconds',type=float,default=12);p.add_argument('--fps',type=float,default=2);p.add_argument('--speed',type=float,default=2);a=p.parse_args();run(a.source,a.output,a.seconds,a.fps,a.speed)
if __name__=='__main__':main()
