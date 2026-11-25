//! M2 experimental resolved source, CPU only. Physical source support shared by
//! momentum and heat; density is independently volume-integrated by transport.
//! No adaptive grid, no imposed downstream curl field, no LES claim.
use crate::runtime::{self as r, Config, Emitter, Error, V3};

#[derive(Clone, Copy, Debug)]
pub struct ResolvedPlumeOptions {
    /// Small axial velocity asymmetry at the source, not a turbulence model.
    pub seed_amplitude: f32,
    pub seed_frequency_hz: f32,
}
impl Default for ResolvedPlumeOptions {
    fn default() -> Self { Self { seed_amplitude: 0., seed_frequency_hz: 0. } }
}
impl ResolvedPlumeOptions {
    pub(crate) fn validate(self) -> Result<(), Error> {
        if !self.seed_amplitude.is_finite() || !(0. ..=0.1).contains(&self.seed_amplitude) ||
            !self.seed_frequency_hz.is_finite() || !(0. ..=50.).contains(&self.seed_frequency_hz) {
            return Err(Error::InvalidArgument("invalid resolved source seed"));
        } Ok(())
    }
}

pub(crate) fn length(e: &Emitter) -> f32 { if e.length > 0. { e.length } else { e.radius } }
pub(crate) fn validate_source(e: &Emitter, c: &Config) -> Result<(), Error> {
    if !e.enabled { return Ok(()); }
    if 2.*e.radius < 4.*c.cell_size || length(e) < 2.*c.cell_size {
        return Err(Error::InvalidArgument("resolved source needs >=4 cells across diameter and >=2 along length"));
    }
    let end = r::add(e.position,r::mul(e.direction,length(e)));
    let extent=c.extent();
    for a in 0..3 {
        let width=e.radius*(1.-e.direction[a]*e.direction[a]).max(0.).sqrt();
        if e.position[a].min(end[a])-width<c.origin[a] || e.position[a].max(end[a])+width>c.origin[a]+extent[a] {
            return Err(Error::InvalidArgument("resolved source must be wholly inside the domain"));
        }
    } Ok(())
}
/// Same physical taper as the conservative scalar source. Unseeded gain uses
/// the legacy 20/s minimum, increased for short residence time at high speed.
pub(crate) fn rate(e: &Emitter) -> f32 { (2.*e.speed/length(e)).max(20.) }

/// Two-point midpoint quadrature along each integrated axis (face area or cell
/// volume). `axis=3` is a cell, otherwise a MAC face normal. Return support and
/// support-weighted target speed multiplier. Seed is a bounded m=1 axial mode
/// only, with a continuous fixed phase and zero mean in a symmetric cylinder.
pub(crate) fn sample(e:&Emitter, world:V3, dx:f32, axis:usize, opt:ResolvedPlumeOptions, time:f64)->(f32,f32) {
    if !e.enabled { return (0.,1.); }
    let l=length(e); let radius=e.radius; let q=r::sub(world,e.position);
    let mid=r::sub(q,r::mul(e.direction,l*0.5));
    if r::len(mid) > (radius*radius+l*l*0.25).sqrt()+dx*0.87 {return (0.,1.);}
    let taper=(radius*0.5).min(l*0.25);
    let seed_dir=if opt.seed_amplitude>0. && axis<3 {
        let helper=if e.direction[1].abs()<0.9 {[0.,1.,0.]} else {[1.,0.,0.]};
        let u0=r::cross(e.direction,helper);let u=r::mul(u0,1./r::len(u0));let v=r::cross(e.direction,u);
        let phase=(std::f64::consts::TAU*time*opt.seed_frequency_hz as f64).rem_euclid(std::f64::consts::TAU);
        let (sin,cos)=phase.sin_cos();r::add(r::mul(u,cos as f32),r::mul(v,sin as f32))
    }else{[0.;3]};
    let(mut weight,mut biased,mut count)=(0.,0.,0.);
    for iz in 0..2 {for iy in 0..2 {for ix in 0..2 {
        let ids=[ix,iy,iz]; if axis<3 && ids[axis]==1 {continue;}
        let delta=std::array::from_fn(|a|if a==axis {0.} else {dx*(ids[a] as f32*0.5-0.25)});
        let point=r::add(q,delta);let along=r::dot(point,e.direction);
        let radial=r::sub(point,r::mul(e.direction,along));let rr=r::len(radial)/radius;
        let w=(1.-r::smooth(rr))*r::smooth(along/taper)*r::smooth((l-along)/taper);
        // Smooth first azimuthal mode, zero on axis and bounded within source.
        let m=1.+opt.seed_amplitude*(r::dot(radial,seed_dir)/radius).clamp(-1.,1.);
        weight+=w;biased+=w*m;count+=1.;
    }}}
    (weight/count,if weight>0. {biased/weight} else {1.})
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn support_and_seed_are_bounded() {
        let e=Emitter{position:[0.1,0.1,0.1],radius:0.02,length:0.04,..Emitter::default()};
        let o=ResolvedPlumeOptions{seed_amplitude:0.05,seed_frequency_hz:2.};
        for i in 0..100 {for a in 0..4 {
            let p=[0.05+i as f32*0.001,0.12,0.1];let (w,m)=sample(&e,p,0.005,a,o,0.13);
            assert!((0. ..=1.).contains(&w));assert!((0.9499..=1.0501).contains(&m));
        }}
        assert_eq!(sample(&e,[0.2,0.2,0.2],0.005,3,o,0.).0,0.);
    }
    #[test] fn symmetry_has_no_net_axial_seed_bias() {
        let e=Emitter{position:[0.,0.,0.],radius:0.02,length:0.04,..Emitter::default()};
        let o=ResolvedPlumeOptions{seed_amplitude:0.05,seed_frequency_hz:2.};
        let (a,b)=sample(&e,[0.01,0.02,0.005],0.005,1,o,0.13);
        let (c,d)=sample(&e,[-0.01,0.02,-0.005],0.005,1,o,0.13);
        assert!((a-c).abs()<1e-6);assert!((b+d-2.).abs()<1e-6);
    }
    #[test] fn unresolved_and_clipped_sources_rejected() {
        let c=Config{cells:[32,32,32],cell_size:0.01,fixed_dt:0.005,max_velocity:3.,..Config::default()};
        let e=Emitter{position:[0.1,0.1,0.1],radius:0.007,length:0.018,..Emitter::default()};
        assert!(validate_source(&e,&c).is_err());
        let e=Emitter{radius:0.03,length:0.04,..e};assert!(validate_source(&e,&c).is_ok());
        let e=Emitter{position:[0.,0.1,0.1],..e};assert!(validate_source(&e,&c).is_err());
    }
}
