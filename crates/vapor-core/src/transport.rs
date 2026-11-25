//! Experimental conservative CPU density path. This is a scalar finite-volume
//! scheme on the existing projected MAC faces, NOT an adaptive momentum solver.
//! Open edges have zero incoming density; closed edges have zero scalar flux.
//! Moving/embedded obstacles are deliberately unsupported by this candidate.
use crate::{Boundary, Config, Emitter, Error};
use crate::solver::{Cell, idx};

#[derive(Clone, Copy, Debug, Default)]
pub struct DensityBudget {
    pub before: f64,
    pub injected: f64,
    pub boundary_outflow: f64,
    pub decayed: f64,
    pub saturated: f64,
    pub after: f64,
    /// Residual includes Float32 storage rounding. Units are density × m³.
    pub residual: f64,
    pub substeps: u32,
}

pub(crate) struct ConservativeDensity {
    q: Vec<f64>,
    predictor: Vec<f64>,
    rate: Vec<f64>,
    injection: Vec<f64>,
    pub budget: Option<DensityBudget>,
}
const CFL: f64 = 0.45;
const MAX_SUBSTEPS: u32 = 256;
const MAX_SOURCE_SAMPLES: usize = 12 * 24 * 12;

fn dense(p: [usize;3], n: [usize;3]) -> usize {
    p[0] + n[0] * (p[1] + n[1] * p[2])
}
fn cells(n: [usize;3]) -> impl Iterator<Item=[usize;3]> {
    (0..n[2]).flat_map(move |z| (0..n[1]).flat_map(move |y| (0..n[0]).map(move |x| [x,y,z])))
}
fn neighbour(p: [usize;3], a: usize, delta: isize, n: [usize;3]) -> Option<[usize;3]> {
    let i = p[a] as isize + delta;
    if i < 0 || i >= n[a] as isize {return None;}
    let mut q = p; q[a] = i as usize; Some(q)
}
fn slope(q: &[f64], p: [usize;3], a: usize, n: [usize;3], boundary: Boundary) -> f64 {
    let mid=q[dense(p,n)];
    let outside=if boundary==Boundary::Closed {mid} else {0.};
    let l=neighbour(p,a,-1,n).map_or(outside,|i|q[dense(i,n)]);
    let r=neighbour(p,a,1,n).map_or(outside,|i|q[dense(i,n)]);
    let (dl,dr)=(mid-l,r-mid);
    if dl*dr<=0. {0.} else {dl.signum()*(2.*dl.abs()).min(2.*dr.abs()).min(0.5*(dl+dr).abs())}
}
/// A shared face is evaluated exactly once and added with opposite signs.
fn rhs(q:&[f64], mac:&[Cell], n:[usize;3], dx:f64, boundary:Boundary, rate:&mut[f64])->f64 {
    rate.fill(0.); let mut out=0.;
    for a in 0..3 {
        let mut faces=n; faces[a]+=1;
        for f in cells(faces) {
            let hi=if f[a]<n[a] {Some(f)} else {None};
            let lo=if f[a]>0 {let mut p=f;p[a]-=1;Some(p)} else {None};
            if boundary==Boundary::Closed && (hi.is_none()||lo.is_none()){continue;}
            let u=mac[idx(f,n)].v[a] as f64;
            let density=if u>=0. {
                lo.map_or(0.,|p|q[dense(p,n)]+0.5*slope(q,p,a,n,boundary))
            } else {hi.map_or(0.,|p|q[dense(p,n)]-0.5*slope(q,p,a,n,boundary))};
            let flux=u*density;
            if let Some(p)=lo {rate[dense(p,n)]-=flux/dx;} else {out-=flux*dx*dx;}
            if let Some(p)=hi {rate[dense(p,n)]+=flux/dx;} else {out+=flux*dx*dx;}
        }
    } out
}
fn substeps(mac:&[Cell],n:[usize;3],dx:f64,dt:f64,boundary:Boundary)->Result<u32,Error>{
    let mut max_out=0f64;
    for p in cells(n) {
        let mut sum=0.;
        for a in 0..3 {
            let mut hi=p;hi[a]+=1;
            let l=mac[idx(p,n)].v[a] as f64;let r=mac[idx(hi,n)].v[a] as f64;
            if !l.is_finite()||!r.is_finite(){return Err(Error::NonFiniteState);}
            if boundary==Boundary::Open||p[a]>0 {sum+=(-l).max(0.);}
            if boundary==Boundary::Open||hi[a]<n[a] {sum+=r.max(0.);}
        } max_out=max_out.max(sum);
    }
    let count=(max_out*dt/(dx*CFL)).ceil().max(1.);
    if count>MAX_SUBSTEPS as f64{return Err(Error::Capacity);}Ok(count as u32)
}
fn finite_nonnegative(q:&[f64])->bool {q.iter().all(|v|v.is_finite()&&*v>=0.)}
fn transport(q:&mut[f64], pred:&mut[f64], rate:&mut[f64], mac:&[Cell], n:[usize;3],dx:f64,dt:f64,boundary:Boundary)->Result<(f64,u32),Error>{
    if !finite_nonnegative(q){return Err(Error::NonFiniteState);}
    let count=substeps(mac,n,dx,dt,boundary)?;let h=dt/count as f64;let mut out=0.;
    for _ in 0..count {
        let f1=rhs(q,mac,n,dx,boundary,rate);
        for i in 0..q.len(){pred[i]=q[i]+h*rate[i];}
        if !finite_nonnegative(pred){return Err(Error::NonFiniteState);}
        let f2=rhs(pred,mac,n,dx,boundary,rate);
        for i in 0..q.len(){q[i]=0.5*q[i]+0.5*(pred[i]+h*rate[i]);}
        if !finite_nonnegative(q){return Err(Error::NonFiniteState);}
        out+=0.5*h*(f1+f2);
    } Ok((out,count))
}
fn smooth(x:f64)->f64{let t=x.clamp(0.,1.);t*t*(3.-2.*t)}
fn cross(a:[f64;3],b:[f64;3])->[f64;3]{[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]}
fn normalized(a:[f64;3])->[f64;3]{let s=a.iter().map(|x|x*x).sum::<f64>().sqrt();a.map(|x|x/s)}
/// Source-space midpoint quadrature: integrate the *physical* cylinder, not a
/// grid-inflated kernel. Nearest finite-volume cell receives each sample. The
/// integral is normalized against the analytic smooth kernel volume. Fully
/// interior sources only (no compensating for clipped or obstructed emission).
/// Momentum and heat still use the production legacy source, intentionally.
fn source(e:&Emitter,cfg:&Config,injection:&mut[f64])->Result<f64,Error>{
    if !e.enabled||e.density_rate==0. {return Ok(0.);}
    let n=cfg.cells.map(|v|v as usize);let dx=cfg.cell_size as f64;
    let p=e.position.map(|v|v as f64);let d=normalized(e.direction.map(|v|v as f64));
    let r=e.radius as f64;let l=if e.length>0.{e.length as f64}else{r};let taper=(r*0.5).min(l*0.25);
    let o=cfg.origin.map(|v|v as f64);
    for a in 0..3 {
        let width=r*(1.-d[a]*d[a]).max(0.).sqrt();let end=p[a]+d[a]*l;
        if p[a].min(end)-width<o[a] || p[a].max(end)+width>o[a]+n[a] as f64*dx {
            return Err(Error::InvalidArgument("conservative source must be fully inside the domain"));
        }
    }
    let helper=if d[1].abs()<0.9 {[0.,1.,0.]}else{[1.,0.,0.]};
    let u=normalized(cross(d,helper));let v=cross(d,u);
    let mut samples=[(0usize,0f64);MAX_SOURCE_SAMPLES];let mut k=0;let mut total=0.;
    for z in 0..12 {
        let h=(z as f64+0.5)*l/12.;let axial=smooth(h/taper)*smooth((l-h)/taper);
        for rr in 0..12 {
            let s=(rr as f64+0.5)/12.;let radial=1.-smooth(s);let weight=axial*radial*s;
            for phi in 0..24 {
                let a=(phi as f64+0.5)*std::f64::consts::TAU/24.;let (sin,cos)=a.sin_cos();
                let pos:[f64;3]=std::array::from_fn(|j|p[j]+d[j]*h+r*s*(u[j]*cos+v[j]*sin));
                let cell=std::array::from_fn(|j|((pos[j]-o[j])/dx).floor().clamp(0.,(n[j]-1) as f64) as usize);
                samples[k]=(dense(cell,n),weight);k+=1;total+=weight;
            }
        }
    }
    if total<=0.||!total.is_finite(){return Err(Error::NonFiniteState);}
    let amount=0.3*std::f64::consts::PI*r*r*(l-taper)*e.density_rate as f64*cfg.fixed_dt as f64;
    let scale=amount/(total*dx.powi(3));
    if !scale.is_finite(){return Err(Error::NonFiniteState);}
    for &(i,w) in &samples[..k]{injection[i]+=w*scale;}
    Ok(amount)
}
impl ConservativeDensity {
    pub fn new(cfg:&Config)->Result<Self,Error>{
        cfg.validate()?;let n=cfg.voxel_count();
        fn allocate(n:usize)->Result<Vec<f64>,Error>{let mut v=Vec::new();v.try_reserve_exact(n).map_err(|_|Error::Capacity)?;v.resize(n,0.);Ok(v)}
        Ok(Self{q:allocate(n)?,predictor:allocate(n)?,rate:allocate(n)?,injection:allocate(n)?,budget:None})
    }
    pub fn bytes(&self)->usize{(self.q.capacity()+self.predictor.capacity()+self.rate.capacity()+self.injection.capacity())*8}
    pub fn prepare(&mut self,cfg:&Config,emitters:&[Option<Emitter>])->Result<(),Error>{
        self.injection.fill(0.);
        for e in emitters.iter().flatten(){source(e,cfg,&mut self.injection)?;}
        if !finite_nonnegative(&self.injection){return Err(Error::NonFiniteState);}Ok(())
    }
    pub fn update(&mut self,src:&[Cell],dst:&mut[Cell],cfg:&Config)->Result<(),Error>{
        self.budget=None;
        let n=cfg.cells.map(|v|v as usize);let dx=cfg.cell_size as f64;let dv=dx.powi(3);let dt=cfg.fixed_dt as f64;
        for p in cells(n){self.q[dense(p,n)]=src[idx(p,n)].s[0] as f64;}
        let before=self.q.iter().sum::<f64>()*dv;
        let (boundary_outflow,substeps)=transport(&mut self.q,&mut self.predictor,&mut self.rate,src,n,dx,dt,cfg.boundary)?;
        let attenuation=(-cfg.density_decay as f64*dt).exp();let mut decayed=0.;let mut saturated=0.;let mut after=0.;
        let injected=self.injection.iter().sum::<f64>()*dv;
        for p in cells(n){let i=dense(p,n);let q=self.q[i];let a=q*attenuation;decayed+=(q-a)*dv;
            let b=a+self.injection[i];let c=b.min(cfg.density_cap as f64);saturated+=(b-c)*dv;
            let f=c as f32;dst[idx(p,n)].s[0]=f;after+=f as f64*dv;}
        let residual=after-(before+injected-boundary_outflow-decayed-saturated);
        self.budget=Some(DensityBudget{before,injected,boundary_outflow,decayed,saturated,after,residual,substeps});Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]fn open_flux_budget_and_positive(){
        let n=[8,6,5];let mut mac=vec![Cell::default();9*7*6];for c in &mut mac{c.v=[0.3,-0.13,0.08,0.];}
        let mut q=vec![0.;8*6*5];for p in cells(n){q[dense(p,n)]=if p[0]>=5&&p[1]<4{0.8}else{0.02};}
        let initial=q.iter().sum::<f64>()*0.01f64.powi(3);let mut pred=q.clone();let mut rate=q.clone();
        let (out,count)=transport(&mut q,&mut pred,&mut rate,&mac,n,0.01,0.12,Boundary::Open).unwrap();
        assert!(count>1&&out>0.&&finite_nonnegative(&q));assert!((q.iter().sum::<f64>()*0.01f64.powi(3)+out-initial).abs()<1e-12);
    }
    #[test]fn closed_domain_has_zero_boundary_flux(){let n=[4,4,4];let mut mac=vec![Cell::default();125];for c in &mut mac{c.v=[1.,-1.,0.,0.];}let mut q=vec![0.5;64];let mut p=q.clone();let mut r=q.clone();let (out,_)=transport(&mut q,&mut p,&mut r,&mac,n,0.1,0.02,Boundary::Closed).unwrap();assert_eq!(out,0.);assert!((q.iter().sum::<f64>()-32.).abs()<1e-12);}
    #[test]fn subcell_source_integrates_at_different_origins(){for dx in [0.012,0.006,0.004] {let cfg=Config{cells:[32,32,32],cell_size:dx,max_velocity:3.,fixed_dt:0.005,..Config::default()};for shift in [0.,0.25,0.5,0.75]{let e=Emitter{position:[0.05+dx*shift,0.03,0.05],direction:[1.,1.,0.],radius:0.007,length:0.018,density_rate:6.,..Emitter::default()}.validated(&cfg).unwrap();let mut q=vec![0.;cfg.voxel_count()];let a=source(&e,&cfg,&mut q).unwrap();assert!(a>0.);assert!((q.iter().sum::<f64>()*(dx as f64).powi(3)/a-1.).abs()<1e-12);}}}
}
