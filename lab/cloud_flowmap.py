"""Detail-preserving cloud deformation via an advected inverse flow map.
Same prescribed MAC curl as cloud_motion; sample ORIGINAL density once per keyframe.
Global bounded scalar normalization (not local conservative transport). Research only.
"""
from __future__ import annotations
import argparse,time,math
from pathlib import Path
from array import array
import numpy as np
from scipy.ndimage import map_coordinates
from cloud_motion import curl_velocity
from vapor_game.field_asset import BakedField,read_field_asset,encode_field_asset
from vapor_game.field_sequence import frame_filename,index_from_paths
from check_sdk import atomic_report

def sample(a,coords):return map_coordinates(a,coords,order=1,mode='nearest',prefilter=False)
def center_velocity(mac):
    u,v,w=mac;return [(w[:-1]+w[1:])*.5,(v[:,:-1]+v[:,1:])*.5,(u[...,:-1]+u[...,1:])*.5]
def step_map(flow,coords,mac,dx,dt):
    if dt<0 or not math.isfinite(dt):raise ValueError('invalid time step')
    vel=np.asarray(center_velocity(mac))/dx
    mid=coords-.5*dt*vel;back=coords-dt*np.stack([sample(a,mid) for a in vel])
    for i,n in enumerate(coords.shape[1:]):back[i]=np.clip(back[i],0,n-1)
    return np.stack([sample(a,back) for a in flow])
def normalize(q,target,cap):
    current=float(q.sum(dtype=np.float64))
    if target==0:return np.zeros_like(q),1.
    if current<=0:raise ArithmeticError('lost all scalar')
    factor=target/current
    if abs(factor-1)>.02:raise ArithmeticError('raw remap mass correction exceeds 2%')
    q=q*factor
    if q.min()<0 or q.max()>cap*(1+1e-6):raise ArithmeticError('remap exceeds scalar bounds')
    return q,factor

def detail_energy(q):return float(sum(np.mean(np.diff(q,axis=a)**2,dtype=np.float64) for a in range(3)))
def run(source,out,seconds=12.,fps=2.,speed=2.):
    f=read_field_asset(source);cells=f.cells;ext=f.extent;dx=ext[0]/cells[0];dv=dx**3
    if not np.allclose(np.array(ext)/cells,dx):raise ValueError('isotropic grid required')
    if not 1<=fps<=12 or not 0<seconds<=120 or abs(seconds*fps-round(seconds*fps))>1e-8:raise ValueError('invalid schedule')
    rho=np.array(f.density,dtype=np.float64).reshape(cells[::-1]);temp=np.array(f.temperature,dtype=np.float64).reshape(cells[::-1]);m0=float(rho.sum());h0=float(temp.sum())
    if not m0>0:raise ValueError('empty field')
    coords=np.indices(rho.shape,dtype=np.float64);flow=coords.copy();out.mkdir(parents=True,exist_ok=True);rows=[];start=time.perf_counter()
    for i in range(round(seconds*fps)+1):
        t=i/fps
        if i:
            # Bounded characteristic motion, midpoint velocity in time.
            sub=max(1,math.ceil(speed/fps/dx/.45));dt=1/fps/sub
            for j in range(sub):flow=step_map(flow,coords,curl_velocity(cells,ext,t-1/fps+(j+.5)*dt,speed),dx,dt)
            r,correction=normalize(sample(rho,flow),m0,f.density_cap);h,hcorrection=normalize(sample(temp,flow),h0,1e5)
        else:r=rho;h=temp;correction=hcorrection=1.;sub=0
        a=r.astype(np.float32);b=h.astype(np.float32);raw=encode_field_asset(BakedField(cells,ext,f.density_cap,f.time+t,array('f',a.ravel()),array('f',b.ravel())))
        (out/frame_filename(i)).write_bytes(raw);row=dict(index=i,time=f.time+t,relative_mass_error=float((a.sum(dtype=np.float64)-m0)/m0),raw_mass_correction=correction,heat_correction=hcorrection,detail_energy=detail_energy(a),relative_shape_change=float(np.abs(a-rho).sum()/m0),peak_density=float(a.max()),substeps=sub);rows.append(row);print('flowmap',i,t,correction,row['detail_energy'],flush=True)
    (out/'sequence.vpa').write_bytes(index_from_paths(out/frame_filename(i) for i in range(len(rows))))
    atomic_report(out/'motion.json',dict(status='PASS',model=__doc__,cells=cells,extent=ext,seconds=seconds,keyframe_fps=fps,speed=speed,elapsed_seconds=time.perf_counter()-start,rows=rows,initial_mass=m0*dv))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('output',type=Path);p.add_argument('--seconds',type=float,default=12);p.add_argument('--fps',type=float,default=2);p.add_argument('--speed',type=float,default=2);a=p.parse_args();run(a.source,a.output,a.seconds,a.fps,a.speed)
if __name__=='__main__':main()
