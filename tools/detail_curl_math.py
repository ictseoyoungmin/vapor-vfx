"""Independent CPU math for the 0.15 shared WGSL detail kernel (not GPU execution).
Coordinates in local metres; two analytic curls of tapered vector potentials.
"""
import numpy as np

TAU=2*np.pi
BANDS=((1.,(1/3,2/3,2/3),(0,1/np.sqrt(2),-1/np.sqrt(2)),21/16,.73,.58),
       (2.3,(2/3,-2/3,1/3),(1/np.sqrt(2),1/np.sqrt(2),0),-34/16,2.17,.42))

def ramp(x):
    t=np.clip(x,0,1);return t*t*(3-2*t),6*t*(1-t)

def wave(q,extent,k,axis,pol,phase,dx):
    resolved=ramp((TAU/(k*dx)-2)*.5)[0]
    if resolved<=0:return np.zeros_like(q)
    width=max(4*dx,3/k)
    l,ld=ramp(q/width);r,rd=ramp((np.asarray(extent)-q)/width)
    m=l*r;dm=(ld*r-l*rd)/width;mask=np.prod(m,axis=-1)
    grad=dm*np.stack((m[...,1]*m[...,2],m[...,0]*m[...,2],m[...,0]*m[...,1]),axis=-1)
    arg=k*np.sum(q*np.asarray(axis),axis=-1)+phase
    return resolved*np.cross((mask*np.cos(arg))[...,None]*np.asarray(axis)+np.sin(arg)[...,None]*grad/k,np.asarray(pol))

def curl(q,extent,k,amplitude,time,dx):
    q=np.asarray(q,dtype=np.float64);out=np.zeros_like(q)
    if amplitude==0:return out
    for mult,axis,pol,hz,phase,weight in BANDS:
        out+=weight*wave(q,extent,k*mult,axis,pol,phase+TAU*((time%16*hz)%1),dx)
    return np.where(np.all((q>0)&(q<np.asarray(extent)),axis=-1)[...,None],amplitude*out,0)

def old_curl(q,k,amplitude,time,origin=(0,0,0)):
    q=(q+np.asarray(origin))*k;s=np.sin(q);c=np.cos(q);sp=np.sin(q+(time%4096)*1.5);cp=np.cos(q+(time%4096)*1.5)
    return amplitude*(sp*np.roll(c,-1,axis=-1)-s*np.roll(cp,1,axis=-1))

# Precompute sin/cos spatial bases; time coefficients recombine linearly. This
# matches the continuous velocity formula at fine cell centres, not exact WGSL
# evaluation at RK2 midpoints (the CPU transport interpolates its velocity grid).
def velocity_bases(q,extent,k,dx,model):
    if model=='none':return np.zeros((0,3,*q.shape[:-1]),np.float32),np.empty(0),np.empty(0)
    if model=='legacy':
        fields=[old_curl(q,k,1,0),old_curl(q,k,1,np.pi/3)]
        return np.stack([np.moveaxis(f,-1,0) for f in fields]).astype(np.float32),np.array([1.5,1.5]),np.array([0,-np.pi/2])
    if model!='curl':raise ValueError('unknown detail model')
    fields=[];freq=[];offset=[]
    for mult,axis,pol,hz,phase,weight in BANDS:
        for extra in (0,np.pi/2):
            fields.append(np.moveaxis(weight*wave(q,extent,k*mult,axis,pol,phase+extra,dx),-1,0));freq.append(TAU*hz);offset.append(-extra)
    return np.stack(fields).astype(np.float32),np.array(freq),np.array(offset)
