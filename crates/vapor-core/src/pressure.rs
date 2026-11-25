//! M2 open-domain pressure candidate. Matrix-free conjugate gradient on
//! A = -h² Laplacian (six neighbours, exterior pressure zero). No obstacles.
//! Reusable f64 work buffers; explicit convergence gate, not fixed SOR passes.
use crate::{Boundary,Config,Error};
use crate::solver::{Cell,idx};

#[derive(Clone,Copy,Debug,Default)]
pub struct PressureReport {
    pub iterations:u32,
    pub initial_divergence_rms:f64,
    pub final_residual_rms:f64,
    /// Actual projected velocity RMS, set only after projection.
    pub projected_divergence_rms:Option<f64>,
}
pub(crate) struct OpenPressure {
    x:Vec<f64>,r:Vec<f64>,p:Vec<f64>,ap:Vec<f64>,
    pub report:Option<PressureReport>,
}
fn apply(q:&[f64],out:&mut[f64],n:[usize;3]) {
    let [nx,ny,nz]=n;let slice=nx*ny;
    for z in 0..nz {for y in 0..ny {for x in 0..nx {
        let i=x+y*nx+z*slice;let mut v=6.*q[i];
        if x>0{v-=q[i-1];}if x+1<nx{v-=q[i+1];}
        if y>0{v-=q[i-nx];}if y+1<ny{v-=q[i+nx];}
        if z>0{v-=q[i-slice];}if z+1<nz{v-=q[i+slice];}
        out[i]=v;
    }}}
}
fn dot(a:&[f64],b:&[f64])->f64 {a.iter().zip(b).map(|(x,y)|x*y).sum()}
impl OpenPressure {
    pub fn new(cfg:&Config)->Result<Self,Error>{
        if cfg.boundary!=Boundary::Open{return Err(Error::Unsupported);}
        let n=cfg.voxel_count();
        fn alloc(n:usize)->Result<Vec<f64>,Error>{let mut v=Vec::new();v.try_reserve_exact(n).map_err(|_|Error::Capacity)?;v.resize(n,0.);Ok(v)}
        Ok(Self{x:alloc(n)?,r:alloc(n)?,p:alloc(n)?,ap:alloc(n)?,report:None})
    }
    pub fn bytes(&self)->usize{(self.x.capacity()+self.r.capacity()+self.p.capacity()+self.ap.capacity())*8}
    pub fn solve(&mut self,mac:&mut[Cell],aux:&[[f32;4]],cfg:&Config)->Result<(),Error>{
        self.report=None;let n=cfg.cells.map(|v|v as usize);let [nx,ny,nz]=n;let h2=(cfg.cell_size as f64).powi(2);let scale=(self.r.len() as f64).sqrt()*h2;
        self.x.fill(0.);
        for z in 0..nz{for y in 0..ny{for x in 0..nx{let i=x+nx*(y+ny*z);self.r[i]=-(aux[idx([x,y,z],n)][3] as f64)*h2;}}}
        self.p.copy_from_slice(&self.r);let mut rr=dot(&self.r,&self.r);
        let initial=rr.sqrt()/scale;
        if !initial.is_finite(){return Err(Error::NonFiniteState);}
        let tolerance=(initial*1e-6).max(1e-7);let mut iterations=0;
        while rr.sqrt()/scale>tolerance && iterations<cfg.pressure_iterations {
            apply(&self.p,&mut self.ap,n);let denom=dot(&self.p,&self.ap);
            if !denom.is_finite()||denom<=0.{return Err(Error::NonFiniteState);}
            let a=rr/denom;
            for i in 0..self.x.len(){self.x[i]+=a*self.p[i];self.r[i]-=a*self.ap[i];}
            let next=dot(&self.r,&self.r);
            if !next.is_finite(){return Err(Error::NonFiniteState);}
            let beta=next/rr;for i in 0..self.p.len(){self.p[i]=self.r[i]+beta*self.p[i];}
            rr=next;iterations+=1;
        }
        // Independently recompute residual, including pressure f32 storage.
        // Never report recursive CG residual as the projected MAC residual.
        for x in &mut self.x{*x=(*x as f32) as f64;}
        apply(&self.x,&mut self.ap,n);
        let mut residual=0.;
        for z in 0..nz{for y in 0..ny{for x in 0..nx{let i=x+nx*(y+ny*z);let b=-(aux[idx([x,y,z],n)][3] as f64)*h2;residual+=(b-self.ap[i]).powi(2);}}}
        let final_rms=residual.sqrt()/scale;
        self.report=Some(PressureReport{iterations,initial_divergence_rms:initial,final_residual_rms:final_rms,projected_divergence_rms:None});
        // Storage rounding can dominate the requested f64 tolerance. Allow a
        // separately stated f32 acceptance floor, still much stricter than SOR.
        if !final_rms.is_finite()||final_rms>(initial*1e-4).max(1e-5){return Err(Error::InvalidArgument("resolved pressure residual exceeds tolerance; refine iteration budget or domain"));}
        for z in 0..nz{for y in 0..ny{for x in 0..nx{mac[idx([x,y,z],n)].s[2]=self.x[x+nx*(y+ny*z)] as f32;}}}
        Ok(())
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]fn manufactured_open_pressure(){
        let c=Config{cells:[18,24,16],cell_size:0.01,fixed_dt:0.005,max_velocity:3.,pressure_iterations:256,..Config::default()};
        let n=c.cells.map(|v|v as usize);let [nx,ny,nz]=n;let mut expected=vec![0.;c.voxel_count()];
        for z in 0..nz{for y in 0..ny{for x in 0..nx{expected[x+nx*(y+ny*z)]=0.01*(std::f64::consts::PI*(x+1) as f64/(nx+1) as f64).sin()*(std::f64::consts::PI*(y+1) as f64/(ny+1) as f64).sin()*(std::f64::consts::PI*(z+1) as f64/(nz+1) as f64).sin();}}}
        let mut b=expected.clone();apply(&expected,&mut b,n);let mut mac=vec![Cell::default();c.padded_len().unwrap()];let mut aux=vec![[0.;4];mac.len()];
        for z in 0..nz{for y in 0..ny{for x in 0..nx{aux[idx([x,y,z],n)][3]=(-b[x+nx*(y+ny*z)]/(c.cell_size as f64).powi(2)) as f32;}}}
        let mut p=OpenPressure::new(&c).unwrap();p.solve(&mut mac,&aux,&c).unwrap();let r=p.report.unwrap();assert!(r.final_residual_rms<r.initial_divergence_rms*1e-4);
        for z in 0..nz{for y in 0..ny{for x in 0..nx{assert!((mac[idx([x,y,z],n)].s[2] as f64-expected[x+nx*(y+ny*z)]).abs()<1e-6);}}}
    }
    #[test]fn zero_rhs_and_nonconvergence(){let c=Config{cells:[8,8,8],pressure_iterations:1,..Config::default()};let mut p=OpenPressure::new(&c).unwrap();let mut mac=vec![Cell::default();c.padded_len().unwrap()];let mut a=vec![[0.;4];mac.len()];p.solve(&mut mac,&a,&c).unwrap();assert_eq!(p.report.unwrap().iterations,0);a[idx([3,3,3],[8,8,8])][3]=1.;assert!(p.solve(&mut mac,&a,&c).is_err());}
}
