"""Experimental finite-volume scalar transport on MAC faces (open boundaries).

MUSCL minmod/SSP-RK2 with explicit outward-flux budget. Not a production solver.
Fields are z,y,x; velocities [u,v,w] in m/s. Zero incoming scalar at open edges.
"""
from __future__ import annotations
import math
import numpy as np


def _flux(q,v,axis,limited):
    a=np.moveaxis(q,axis,0);u=np.moveaxis(v,axis,0)
    if u.shape!=(a.shape[0]+1,*a.shape[1:]):raise ValueError('invalid staggered face shape')
    p=np.pad(a,[(1,1),(0,0),(0,0)],mode='constant')
    if limited:
        dl=a-p[:-2];dr=p[2:]-a
        # monotonized central limiter: both reconstructed faces are nonnegative for q>=0.
        slope=np.where(dl*dr>0,np.sign(dl)*np.minimum(np.minimum(2*np.abs(dl),2*np.abs(dr)),.5*np.abs(dl+dr)),0.)
    else:slope=np.zeros_like(a)
    left=np.concatenate((np.zeros_like(a[:1]),a+.5*slope),axis=0)
    right=np.concatenate((a-.5*slope,np.zeros_like(a[:1])),axis=0)
    f=u*np.where(u>=0,left,right)
    # positive outward scalar flux across the two domain faces (incoming exterior scalar=0)
    out=float(f[-1].sum()-f[0].sum())
    return np.moveaxis(np.diff(f,axis=0),0,axis),out


def transport(q,velocities,dx,dt,*,limited=True):
    """Returns (new scalar field, integrated boundary mass outflow, substep count).

    No clipping/renormalization: a failed nonnegative check raises. Open faces
    carry zero external scalar. Velocity is frozen over the requested interval.
    """
    q=np.array(q,dtype=np.float64,copy=True);v=[np.asarray(u,dtype=np.float64) for u in velocities]
    if q.ndim!=3 or len(v)!=3 or not math.isfinite(dx) or dx<=0 or not math.isfinite(dt) or dt<0 or not np.all(np.isfinite(q)) or np.min(q)<0:raise ValueError('invalid transport input')
    outgoing=np.zeros_like(q)
    for i,u in enumerate(v):
        axis=2-i;shape=list(q.shape);shape[axis]+=1
        if u.shape!=tuple(shape) or not np.all(np.isfinite(u)):raise ValueError('invalid MAC velocity')
        a=np.moveaxis(u,axis,0);outgoing+=np.moveaxis(np.maximum(a[1:],0)+np.maximum(-a[:-1],0),0,axis)
    count=max(1,math.ceil(dt/dx*float(outgoing.max())/.45))
    if count>256:raise ValueError('CFL substep budget exceeded')
    h=dt/count;loss=0.
    def rhs(a):
        rate=np.zeros_like(a);out=0.
        for i,u in enumerate(v):
            diff,boundary=_flux(a,u,2-i,limited);rate-=diff/dx;out+=boundary*dx*dx
        return rate,out
    for _ in range(count):
        k1,f1=rhs(q);pred=q+h*k1;k2,f2=rhs(pred);q=.5*q+.5*(pred+h*k2);loss+=.5*h*(f1+f2)
        if not np.all(np.isfinite(q)) or np.min(q)<-1e-12:raise ArithmeticError('nonfinite or negative scalar')
    return q,loss,count
