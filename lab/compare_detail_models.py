#!/usr/bin/env python3
"""Actual independent CPU MAC + fine transport, NOT Rust/WGSL execution.
Compare identical coarse velocities, source, fine grid and optics with three
fine velocity models. Requires NumPy/SciPy/Numba/Pillow/Node.js.
"""
from pathlib import Path
import argparse,json,subprocess,tempfile,time,sys
import numpy as np
from numba import njit,prange,set_num_threads
import bootstrap  # enables explicit shared validation helpers
from reference_fluid import Reference,weights,lattice
from reference_detail import velocity,trace,scalar,bounds
from detail_curl_math import velocity_bases
from quality_metrics import density_summary,timing_summary
from runtime_common import ROOT,sha256
from check_sdk import atomic_report

MODES=('none','legacy','curl')
OPTIONS={'cigarette_smoke':(.10,100.),'exhaled_aerosol':(.24,70.)}

@njit(parallel=True)
def transport_limited(rho,temp,vel,pred,pt,out,ot,source,dt,decay,cool,cap,rate,heat):
    nz,ny,nx=rho.shape
    for z in prange(nz):
      for y in range(ny):
       for x in range(nx):
        a,b,c=trace(vel,x,y,z,dt);pred[z,y,x]=scalar(rho,a,b,c);pt[z,y,x]=scalar(temp,a,b,c)
    for z in prange(nz):
      for y in range(ny):
       for x in range(nx):
        a,b,c=trace(vel,x,y,z,dt);u,v,w=trace(vel,x,y,z,-dt)
        if a<-.5 or b<-.5 or c<-.5 or a>nx-.5 or b>ny-.5 or c>nz-.5:r=0.;t=0.
        else:
         lo,hi=bounds(rho,a,b,c);lt,ht=bounds(temp,a,b,c)
         gain=min(1.,2./max(1.,np.sqrt((a-x)**2+(b-y)**2+(c-z)**2)))
         rp=pred[z,y,x];tp=pt[z,y,x]
         r=rp+gain*(max(lo,min(hi,rp+.5*(rho[z,y,x]-scalar(pred,u,v,w))))-rp)
         t=tp+gain*(max(lt,min(ht,tp+.5*(temp[z,y,x]-scalar(pt,u,v,w))))-tp)
        s=source[z,y,x];r=max(0.,r)*decay;t=max(0.,t)*cool
        out[z,y,x]=min(cap,r+rate*s*dt);ot[z,y,x]=t+max(0.,heat-t)*(1-np.exp(-20*s*dt))

class Variant:
    def __init__(self,model,q,extent,k,dx,amp):
        shape=q.shape[:-1];self.name=model;self.rho=np.zeros(shape,np.float32);self.temp=self.rho.copy();self.out=self.rho.copy();self.ot=self.temp.copy();self.basis,self.freq,self.phase=velocity_bases(q,extent,k,dx,model);self.amp=amp;self.dx=dx;self.timings=[]
    def step(self,base,vel,pred,pt,src,age,dt,decay,cool,cap,rate,heat):
        start=time.perf_counter();np.copyto(vel,base)
        if self.name!='none':
            coeff=(self.amp*np.cos(self.freq*age+self.phase)/self.dx).astype(np.float32)
            for i,c in enumerate(coeff):vel+=c*self.basis[i]
        transport_limited(self.rho,self.temp,vel,pred,pt,self.out,self.ot,src,dt,decay,cool,cap,rate,heat)
        self.rho,self.out=self.out,self.rho;self.temp,self.ot=self.ot,self.temp;self.timings.append((time.perf_counter()-start)*1000)

def run(args,folder,report):
    data=json.loads((ROOT/'effects/presets.json').read_text());rows=[]
    for key in args.presets:
        preset=next(x for x in data['presets'] if x['key']==key);s=Reference(preset,'medium',False);amp,k=OPTIONS[key];scale=args.scale;dx=s.dx/scale;cells=[n*scale for n in s.c['cells']];shape=tuple(reversed(cells));extent=np.array(cells)*dx
        p=lattice(shape,3);q=np.moveaxis(p,0,-1)[...,::-1]*dx;source=weights(p,s.e,dx,s.axis);r=s.e['radius'];l=s.e['length'] or r;source_scale=(r/max(r,dx*1.1))**2*l/max(l,dx)
        variants=[Variant(mode,q,extent,k,dx,amp) for mode in MODES];base=np.zeros((3,*shape),np.float32);vel=base.copy();pred=np.zeros(shape,np.float32);pt=pred.copy();decay=np.exp(-s.c['densityDecay']*s.dt);cool=np.exp(-s.c['cooling']*s.dt);empty=np.zeros((0,3,*shape),np.float32);coeff=np.empty(0,np.float32)
        start=time.perf_counter()
        for i in range(args.ticks):
            age=s.ticks*s.dt;active=not s.p or age<s.p['duration'];rate=s.e['densityRate'] if active else 0.;heat=s.e['temperature'] if active else 0.
            if active and s.curve is not None:
                f=s.curve(age/s.p['duration']);rate*=np.clip(f[1],0,1)*max(0.,f[2])
            s.step();velocity(*s.v,base,empty,coeff,scale,dx)
            for variant in variants:variant.step(base,vel,pred,pt,source,age,s.dt,decay,cool,s.c['densityCap'],rate*source_scale,heat)
            if (i+1)%30==0:print(key,'ticks',i+1,'seconds',round(time.perf_counter()-start,1),flush=True)
        for v in variants:
            if not np.isfinite(v.rho).all() or not np.isfinite(v.temp).all() or not np.any(v.rho>0):raise RuntimeError('invalid scalar result')
            stem=key+'-'+v.name;spec=dict(effect=key,model=v.name,cells=cells,extent=extent.tolist(),densityCap=s.c['densityCap'],material=preset['material'],time=s.ticks*s.dt,source=s.e['position'],direction=s.axis.tolist())
            (folder/(stem+'.json')).write_text(json.dumps(spec));d=folder/(stem+'.density.f32');t=folder/(stem+'.temperature.f32');v.rho.astype('<f4').tofile(d);v.temp.astype('<f4').tofile(t)
            summary=density_summary(v.rho,cells=cells,extent=extent,cap=s.c['densityCap'],source=s.e['position'],direction=s.axis)
            rows.append(dict(key=key,model=v.name,cells=cells,coarse_cells=s.c['cells'],time=spec['time'],amplitude=amp if v.name!='none' else 0,base_wave_number=k,injection_scale=source_scale,density_sha256=sha256(d),temperature_sha256=sha256(t),coarse_clamps=s.clamps,timing_including_jit=timing_summary(v.timings),**summary));print(stem,summary['plume'],flush=True)
        report['fields']=rows;atomic_report(args.output/'comparison.json',report)
    subprocess.run(['node',str(ROOT/'lab/render_detail_comparison.mjs'),str(folder),str(args.output),*args.presets],check=True,cwd=ROOT)
    from PIL import Image,ImageDraw,ImageFont
    for key in args.presets:
        imgs=[Image.open(args.output/(key+'-'+m+'.png')).convert('RGB') for m in MODES];w,h=imgs[0].size;sheet=Image.new('RGB',(3*w+48,h+68),'#111923');draw=ImageDraw.Draw(sheet);font=ImageFont.load_default(size=16);draw.text((12,12),f'{key.replace("_"," ")} | independent CPU fine transport | {args.scale}x scalar, {args.ticks} ticks',font=font,fill='#e6edf6')
        for i,(img,label) in enumerate(zip(imgs,['No detail velocity','0.14 analytic curl','0.15 tapered two-band curl'])):
            x=12+i*(w+12);sheet.paste(img,(x,38));draw.text((x,h+44),label,font=font,fill='#d3deed')
        path=args.output/(key+'-comparison.png');sheet.save(path)
    report.update(status='PASS',complete=True,images=[dict(file=p.name,sha256=sha256(p)) for p in sorted(args.output.glob('*.png'))]);atomic_report(args.output/'comparison.json',report)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--scale',type=int,choices=[2,3,4],default=4);p.add_argument('--ticks',type=int,default=120);p.add_argument('--threads',type=int,default=4);p.add_argument('--presets',nargs='+',choices=list(OPTIONS),default=list(OPTIONS));p.add_argument('--output',type=Path,default=ROOT/'reports/local/lab/detail');p.add_argument('--keep-fields',action='store_true');a=p.parse_args();a.output=a.output.resolve();a.output.mkdir(parents=True,exist_ok=True);set_num_threads(a.threads)
    if not 1<=a.ticks<=600:p.error('ticks 1..600')
    for key in a.presets:
        for name in (*MODES,'comparison'):(a.output/(key+'-'+name+'.png')).unlink(missing_ok=True)
    report=dict(status='RUNNING',complete=False,evidence='Independent CPU spectral MAC + actual fine scalar advection, NOT Rust or WGSL execution. Same coarse fields and source; numerical midpoint uses interpolated fine velocity rather than analytic GPU evaluation.',fields=[],source_sha256=sha256(ROOT/'shaders/compute/detail.wgsl'))
    atomic_report(a.output/'comparison.json',report)
    try:
        if a.keep_fields:
            folder=a.output/'fields';folder.mkdir(exist_ok=True);run(a,folder,report)
        else:
            with tempfile.TemporaryDirectory(prefix='vapor-detail-') as d:run(a,Path(d),report)
    except Exception as e:
        report.update(status='FAIL',complete=True,error=str(e));atomic_report(a.output/'comparison.json',report);raise
if __name__=='__main__':main()
