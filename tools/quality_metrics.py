"""Physical-coordinate field diagnostics, independent of solver and rendering.
Density integral is a simulation-unit integral, not measured aerosol mass in kg.
Empty fields are valid; undefined plume statistics are represented by null.
"""
from __future__ import annotations
import math
import numpy as np

MAX_VOXELS=2097152

def _grid(cells,extent,origin):
    if len(cells)!=3 or any(type(v) is not int or v<1 or v>768 for v in cells) or math.prod(cells)>MAX_VOXELS:
        raise ValueError('invalid diagnostic grid')
    e=np.asarray(extent,dtype=np.float64);o=np.asarray(origin,dtype=np.float64)
    if e.shape!=(3,) or o.shape!=(3,) or not np.all(np.isfinite(e)) or not np.all(e>0) or not np.all(np.isfinite(o)):
        raise ValueError('invalid extent/origin')
    return e/np.asarray(cells),o

def _weighted_quantiles(values,weights,quantiles):
    # Weighted empirical quantiles at cell centres. No interpolation or invented
    # extent between discrete samples. Stable sorting makes ties deterministic.
    order=np.argsort(values,kind='stable');v=values[order];w=weights[order]
    c=np.cumsum(w,dtype=np.float64)
    i=np.searchsorted(c,np.asarray(quantiles)*c[-1],side='left')
    return [float(v[min(j,len(v)-1)]) for j in i]

def density_summary(density,*,cells,extent,origin=(0,0,0),cap=None,source=None,direction=None):
    dx,o=_grid(cells,extent,origin);nx,ny,nz=cells
    rho=np.asarray(density,dtype=np.float64)
    if rho.shape!=(nz,ny,nx) or not np.all(np.isfinite(rho)) or np.any(rho<0):raise ValueError('invalid density field shape/value')
    if cap is not None and (not math.isfinite(cap) or cap<=0 or np.any(rho>cap+max(1e-6,cap*1e-6))):raise ValueError('density outside configured cap')
    if (source is None)!=(direction is None):raise ValueError('source and direction must be supplied together')
    if source is not None:
        src=np.asarray(source,dtype=np.float64);axis=np.asarray(direction,dtype=np.float64)
        if src.shape!=(3,) or axis.shape!=(3,) or not np.all(np.isfinite(src)) or not np.all(np.isfinite(axis)) or not math.isfinite(float(np.linalg.norm(axis))) or np.linalg.norm(axis)<1e-12:raise ValueError('invalid plume axis')
        axis=axis/np.linalg.norm(axis)
    z,y,x=np.nonzero(rho>0);w=rho[z,y,x];total=float(w.sum(dtype=np.float64));dv=float(np.prod(dx))
    out={'density_integral':total*dv,'occupied_voxels':int(len(w)),'occupied_fraction':len(w)/rho.size,'max_density':float(rho.max()),'cell_size_xyz':dx.tolist(),'centroid_world':None,'rms_spread_xyz':None,'bounds_min_world':None,'bounds_max_world':None,'outer_cell_mass_fraction':None,'saturation_mass_fraction':None,'plume':None}
    if not len(w):return out
    p=np.column_stack((x,y,z));world=o+(p+.5)*dx
    centroid=np.sum(world*w[:,None],axis=0)/total
    outer=np.any((p==0)|(p==np.asarray(cells)-1),axis=1)
    out.update(centroid_world=centroid.tolist(),rms_spread_xyz=np.sqrt(np.sum((world-centroid)**2*w[:,None],axis=0)/total).tolist(),bounds_min_world=(o+p.min(axis=0)*dx).tolist(),bounds_max_world=(o+(p.max(axis=0)+1)*dx).tolist(),outer_cell_mass_fraction=float(w[outer].sum()/total))
    if cap is not None:out['saturation_mass_fraction']=float(w[w>=cap*(1-1e-6)].sum()/total)
    if source is not None:
        offset=world-src;axial=offset@axis;radial=offset-axial[:,None]*axis
        out['plume']={'source_world':src.tolist(),'direction':axis.tolist(),'axial_q05_q50_q95':_weighted_quantiles(axial,w,[.05,.5,.95]),'forward_mass_fraction':float(w[axial>=0].sum()/total),'backward_mass_fraction':float(w[axial<0].sum()/total),'radial_rms':float(np.sqrt(np.sum(np.sum(radial**2,axis=1)*w)/total)),'axial_mean':float(np.dot(axial,w)/total)}
    return out

def atlas_summary(atlas,*,cells,extent,density_cap,origin=(0,0,0),source=None,direction=None):
    _grid(cells,extent,origin)
    if not math.isfinite(density_cap) or density_cap<=0:raise ValueError('invalid density cap')
    nx,ny,nz=cells;raw=np.frombuffer(atlas,dtype=np.uint8)
    if raw.size!=nx*ny*nz*4:raise ValueError('invalid atlas byte count')
    a=raw.reshape(nz,ny,nx,4)
    if np.any(a[...,3]!=255) or np.any((a[...,2]!=0)&(a[...,2]!=255)):raise ValueError('invalid alpha/solid channel')
    if np.any((a[...,2]==255)&(a[...,0]>0)):raise ValueError('density in solid atlas cells')
    out=density_summary(a[...,0].astype(np.float64)*(density_cap/255),cells=cells,extent=extent,origin=origin,cap=density_cap,source=source,direction=direction)
    out.update(encoding='RGBA8 quantized render field',density_quantization_step=density_cap/255)
    return out

def timing_summary(values):
    a=np.asarray(values,dtype=np.float64)
    if a.ndim!=1 or not len(a) or not np.all(np.isfinite(a)) or np.any(a<0):raise ValueError('invalid timing samples')
    return {'count':len(a),'mean_ms':float(a.mean()),'p50_ms':float(np.percentile(a,50)),'p95_ms':float(np.percentile(a,95)),'p99_ms':float(np.percentile(a,99)),'max_ms':float(a.max()),'total_ms':float(a.sum())}
