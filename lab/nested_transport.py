"""Fixed 3-D fine/coarse slab interface research, NOT a coupled momentum/pressure solver.

One shared scalar flux is integrated on fine faces; area-restricted flux enters
coarse cells with opposite sign. Global SSP-RK2 uses fine CFL. MUSCL away from
interface; first order on nonconforming interface. Open exterior, zero inflow.
All arrays are z,y,x. This is a prescribed-velocity scalar experiment only.
"""
import math
import numpy as np

def _restricted(a,r):
    z,y=a.shape
    return a.reshape(z//r,r,y//r,r).mean(axis=(1,3))

def _faces(q,v,axis):
    a=np.moveaxis(q,axis,0);u=np.moveaxis(v,axis,0)
    p=np.pad(a,[(1,1),(0,0),(0,0)]);dl=a-p[:-2];dr=p[2:]-a
    slope=np.where(dl*dr>0,np.sign(dl)*np.minimum(np.minimum(2*np.abs(dl),2*np.abs(dr)),.5*np.abs(dl+dr)),0.)
    left=np.concatenate((np.zeros_like(a[:1]),a+.5*slope),axis=0)
    right=np.concatenate((a-.5*slope,np.zeros_like(a[:1])),axis=0)
    return u*np.where(u>=0,left,right)

def advance(fine,coarse,vf,vc,dx,ratio,dt):
    """Advance adjacent fine-left and coarse-right scalar grids over dt.
    vf,vc = MAC x/y/z velocities. Interface normal velocity must be area-consistent.
    Returns arrays and integrated outer outflow / signed fine-to-coarse transfer.
    """
    if type(ratio) is not int or ratio not in (2,4) or not math.isfinite(dx) or dx<=0 or not math.isfinite(dt) or dt<0:raise ValueError('invalid geometry or time')
    f,c=[np.array(q,dtype=np.float64,copy=True) for q in (fine,coarse)];dx2=dx*ratio
    if f.ndim!=3 or c.ndim!=3 or min(f.shape+c.shape)<2 or f.shape[:2]!=tuple(n*ratio for n in c.shape[:2]):raise ValueError('unaligned interface')
    def validate(q,vs,h):
        if len(vs)!=3 or not np.isfinite(q).all() or np.min(q)<0:raise ValueError('invalid scalar')
        out=np.zeros_like(q);v=[]
        for i,a in enumerate(vs):
            a=np.asarray(a,dtype=np.float64);shape=list(q.shape);axis=2-i;shape[axis]+=1
            if a.shape!=tuple(shape) or not np.isfinite(a).all():raise ValueError('invalid velocity')
            v.append(a);u=np.moveaxis(a,axis,0);out+=np.moveaxis(np.maximum(u[1:],0)+np.maximum(-u[:-1],0),0,axis)
        return v,float(out.max())/h
    vf,cf=validate(f,vf,dx);vc,cc=validate(c,vc,dx2)
    u=vf[0][:,:,-1];uc=vc[0][:,:,0];restriction=_restricted(u,ratio)
    if not np.allclose(restriction,uc,rtol=1e-10,atol=1e-12):raise ValueError('inconsistent interface normal velocity')
    steps=max(1,math.ceil(dt*max(cf,cc)/.45));
    if steps>256:raise ValueError('CFL budget')
    h=dt/steps
    def rhs(a,b):
        fs=[_faces(a,v,2-i) for i,v in enumerate(vf)];cs=[_faces(b,v,2-i) for i,v in enumerate(vc)]
        donor=np.repeat(np.repeat(b[:,:,0],ratio,axis=0),ratio,axis=1)
        interface=u*np.where(u>=0,a[:,:,-1],donor)
        fs[0][-1]=interface;cs[0][0]=_restricted(interface,ratio)
        def region(q,flux,hx):
            rate=np.zeros_like(q);out=0.
            for i,g in enumerate(flux):rate-=np.moveaxis(np.diff(g,axis=0),0,2-i)/hx;out+=float(g[-1].sum()-g[0].sum())*hx*hx
            return rate,out
        ra,oa=region(a,fs,dx);rb,ob=region(b,cs,dx2);transfer=float(interface.sum())*dx*dx
        # Region budgets count interface twice with opposite signs. Explicitly remove it from exterior outflow.
        exterior=(oa-transfer)+(ob+transfer)
        return ra,rb,exterior,transfer
    out=transfer=0.
    for _ in range(steps):
        a,b,o,t=rhs(f,c);pf,pc=f+h*a,c+h*b;a,b,o2,t2=rhs(pf,pc)
        f=.5*f+.5*(pf+h*a);c=.5*c+.5*(pc+h*b);out+=.5*h*(o+o2);transfer+=.5*h*(t+t2)
        if not np.isfinite(f).all() or not np.isfinite(c).all() or min(f.min(),c.min())< -1e-12:raise ArithmeticError('negative or nonfinite scalar')
    return f,c,dict(outer_outflow=out,interface_transfer=transfer,substeps=steps)

def constant_velocity(shape,u):
    z,y,x=shape
    return [np.full((z,y,x+1),u),np.zeros((z,y+1,x)),np.zeros((z+1,y,x))]
