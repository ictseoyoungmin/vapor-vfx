"""Evaluate high-resolution original cloud with a coarse inverse flow map.
One resampling of the original hero density, bounded global mass normalization.
Not a high-resolution velocity solve and not meteorological dynamics.
"""
from __future__ import annotations
import argparse,json,math,time
from array import array
from pathlib import Path
import numpy as np
from cloud_flowmap import step_map,sample,normalize,detail_energy
from cloud_motion import curl_velocity
from vapor_game.field_asset import BakedField,read_field_asset,encode_field_asset
from check_sdk import atomic_report

def run(preview,hero,out,seconds=12.):
    a=read_field_asset(preview);b=read_field_asset(hero)
    if a.extent!=b.extent or a.density_cap!=b.density_cap or a.time!=b.time:raise ValueError('reference scene mismatch')
    cells=a.cells;ext=a.extent;dx=ext[0]/cells[0];shape=cells[::-1];hshape=b.cells[::-1];coords=np.indices(shape,dtype=np.float64);flow=coords.copy();dt=.25
    for i in range(round(seconds/dt)):
        flow=step_map(flow,coords,curl_velocity(cells,ext,(i+.5)*dt,2.),dx,dt)
    # Use physical displacement, not absolute coordinate interpolation at boundaries.
    hcoords=np.indices(hshape,dtype=np.float64);ratio=np.array(shape,dtype=np.float64)/hshape;coarse=(hcoords+.5)*ratio[:,None,None,None]-.5
    warped=hcoords.copy()
    for i in range(3):warped[i]+=sample(flow[i]-coords[i],coarse)/ratio[i]
    rho=np.array(b.density,dtype=np.float64).reshape(hshape);temp=np.array(b.temperature,dtype=np.float64).reshape(hshape);target=float(rho.sum());r,g=normalize(sample(rho,warped),target,b.density_cap);h,hg=normalize(sample(temp,warped),float(temp.sum()),1e5);r=r.astype(np.float32);h=h.astype(np.float32)
    out.mkdir(parents=True,exist_ok=True);(out/'hero-t12.vpf').write_bytes(encode_field_asset(BakedField(b.cells,b.extent,b.density_cap,b.time+seconds,array('f',r.ravel()),array('f',h.ravel()))));atomic_report(out/'hero-deform.json',dict(status='PASS',scope=__doc__,seconds=seconds,velocity_grid=cells,hero_grid=b.cells,mass_correction=g,heat_correction=hg,relative_mass_error=float((r.sum(dtype=np.float64)-target)/target),detail_energy_before=detail_energy(rho),detail_energy_after=detail_energy(r)))
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('preview',type=Path);p.add_argument('hero',type=Path);p.add_argument('output',type=Path);a=p.parse_args();run(a.preview,a.hero,a.output)
