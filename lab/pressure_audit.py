"""Matrix-free CG audit against exact open-grid DST and old RB-SOR math.
Independent NumPy float64 CG/f32 stored pressure; not Rust runtime/timing.
"""
from __future__ import annotations
import argparse,json,time
from pathlib import Path
import numpy as np
from scipy.fft import dstn,idstn
import bootstrap
from runtime_common import ROOT
from check_sdk import atomic_report
from reference_fluid import Reference,divergence
from resolved_plume import local_preset,source_basis,CASES

def apply(q):
    r=6*q.copy();r[:,:,1:]-=q[:,:,:-1];r[:,:,:-1]-=q[:,:,1:];r[:,1:,:]-=q[:,:-1,:];r[:,:-1,:]-=q[:,1:,:];r[1:]-=q[:-1];r[:-1]-=q[1:];return r

def cg(b,dx,cap=256):
    x=np.zeros_like(b,dtype=np.float64);r=b.astype(np.float64).copy();p=r.copy();rr=float(np.sum(r*r));scale=np.sqrt(b.size)*dx*dx;initial=np.sqrt(rr)/scale;tol=max(1e-7,initial*1e-6);i=0
    while np.sqrt(rr)/scale>tol and i<cap:
        ap=apply(p);denom=float(np.sum(p*ap));
        if denom<=0:raise ArithmeticError('CG nonpositive denominator')
        a=rr/denom;x+=a*p;r-=a*ap;next_rr=float(np.sum(r*r));p=r+(next_rr/rr)*p;rr=next_rr;i+=1
    return x.astype(np.float32),i

def sor(b,iterations,omega=1.7):
    b=b.astype(np.float32);p=np.zeros_like(b);red=np.indices(b.shape).sum(axis=0)%2==0
    for _ in range(iterations):
        for mask in (red,~red):
            err=(b-apply(p))/6;p[mask]+=omega*err[mask]
    return p,iterations

def exact(b):
    ez,ey,ex=[2-2*np.cos(np.pi*np.arange(1,n+1)/(n+1)) for n in b.shape]
    return idstn(dstn(b,type=1,norm='ortho')/(ez[:,None,None]+ey[None,:,None]+ex[None,None,:]),type=1,norm='ortho')

def evaluate(b,dx):
    ref=exact(b);initial=float(np.sqrt(np.mean(b*b))/dx**2);result={}
    for label,fn in [('sor32',lambda:sor(b,32)),('sor256',lambda:sor(b,256)),('cg256',lambda:cg(b,dx))]:
        q,it=fn();res=float(np.sqrt(np.mean((b-apply(q.astype(np.float64)))**2))/dx**2);result[label]=dict(iterations=it,residual_rms=res,relative_residual=res/max(initial,1e-30),relative_pressure_l2=float(np.linalg.norm(q-ref)/max(np.linalg.norm(ref),1e-30)))
    result['initial_divergence_rms']=initial
    result['cg_gate']=result['cg256']['residual_rms']<=max(initial*1e-4,1e-5)
    return result

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,default=ROOT/'reports/research-pressure.json');a=ap.parse_args();rows=[];catalog={p['key']:p for p in json.loads((ROOT/'effects/presets.json').read_text())['presets']}
    for key in CASES:
        s=Reference(local_preset(catalog[key]),'medium',False);dx=s.dx;z,y,x=np.indices(s.rho.shape,dtype=np.float64);z=(z+1)/(s.rho.shape[0]+1);y=(y+1)/(s.rho.shape[1]+1);x=(x+1)/(s.rho.shape[2]+1)
        p=.01*np.sin(np.pi*x)*np.sin(np.pi*y)*np.sin(np.pi*z)+.003*np.sin(5*np.pi*x)*np.sin(3*np.pi*y)*np.sin(2*np.pi*z)
        b=apply(p);r=evaluate(b,dx);rows.append(dict(key=key,case='manufactured_low_and_high_frequency',cells=s.c['cells'],**r));print(key,'manufactured',r['cg256'],flush=True)
        v=[]
        for axis,pts in enumerate(s.pv):
            w,_,_=source_basis(pts,s.e,dx,axis,s.axis);v.append((s.axis[axis]*s.e['speed']*(1-np.exp(-max(20.,2*s.e['speed']/(s.e['length'] or s.e['radius']))*w*s.dt))).astype(np.float32))
        b=-divergence(v,dx).astype(np.float64)*dx**2;r=evaluate(b,dx);rows.append(dict(key=key,case='local_source_velocity',cells=s.c['cells'],**r));print(key,'source',r['cg256'],flush=True)
    status='PASS' if all(r['cg_gate'] for r in rows) else 'FAIL';atomic_report(a.output,dict(status=status,evidence=__doc__,rows=rows));return 0 if status=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
