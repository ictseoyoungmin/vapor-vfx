//! Game effect catalog and a bounded, deterministic procedural volume generator.
//! Procedural humidity is an artistic saturation proxy, not atmospheric thermodynamics.
use crate::{Config,Boundary,Emitter,Error,V3};
mod generated;
#[repr(C)]
#[derive(Clone,Copy,Debug)]
pub struct Material {pub colour:V3,pub extinction:f32,pub anisotropy:f32,pub albedo:f32,pub emission:f32,pub thermal_fade:f32,pub ambient:f32}
#[derive(Clone,Copy,Debug)]
pub struct ProceduralSettings {pub seed:u32,pub coverage:f32,pub humidity:f32,pub wind:V3,pub erosion:f32}
#[derive(Clone,Debug)]
pub struct Preset {pub id:u32,pub key:&'static str,pub kind:u32,pub config:Config,pub emitter:Emitter,pub material:Material,pub procedural:Option<ProceduralSettings>,pub profile:&'static [[f64;4]],pub duration:f64,pub ember:bool}
#[derive(Clone,Debug)]
pub struct EffectDefinition {pub preset:Preset,pub ray_steps:u32,pub upload_hz:u32}
/// Quality 0/1/2: low/medium/high. Physical size and emitter parameters are unchanged.
pub fn preset(id:u32,quality:u32)->Result<EffectDefinition,Error>{
    let mut p=generated::base(id).ok_or(Error::InvalidArgument("unknown effect preset"))?;
    let (scale,pressure,ray_steps,fluid_hz,proc_hz)=generated::quality(quality).ok_or(Error::InvalidArgument("unknown quality"))?;
    p.config.cells=p.config.cells.map(|x|(x as f32*scale) as u32);
    p.config.cell_size/=scale;p.config.pressure_iterations=pressure;
    p.config.validate()?;p.emitter.clone().validated(&p.config)?;
    let upload_hz=if p.kind==0{fluid_hz}else{proc_hz};
    Ok(EffectDefinition{preset:p,ray_steps,upload_hz})
}
fn smooth(a:f64,b:f64,x:f64)->f64{let t=((x-a)/(b-a)).clamp(0.,1.);t*t*(3.-2.*t)}
fn hash(x:i32,y:i32,z:i32,seed:u32)->f64{
    let mut h=seed^((x as u32)&255).wrapping_mul(0x9e3779b1)^((y as u32)&255).wrapping_mul(0x85ebca77)^((z as u32)&255).wrapping_mul(0xc2b2ae3d);
    h^=h>>16;h=h.wrapping_mul(0x7feb352d);h^=h>>15;h=h.wrapping_mul(0x846ca68b);h^=h>>16;
    h as f64/4294967295.
}
fn noise(p:[f64;3],seed:u32)->f64{
    let i=p.map(|x|x.floor() as i32);let f=[0,1,2].map(|a|{let t=p[a]-p[a].floor();t*t*(3.-2.*t)});
    let mut v=0.;for z in 0..2{for y in 0..2{for x in 0..2{let w=[x,y,z];let weight=(0..3).map(|a|if w[a]==0{1.-f[a]}else{f[a]}).product::<f64>();v+=weight*hash(i[0]+x,i[1]+y,i[2]+z,seed);}}}v
}
const LOBES:[[f64;6];6]=[[0.24,0.38,0.48,0.23,0.25,0.30],[0.43,0.48,0.51,0.25,0.38,0.31],[0.61,0.48,0.50,0.27,0.37,0.30],[0.77,0.38,0.48,0.20,0.24,0.26],[0.43,0.66,0.48,0.18,0.26,0.22],[0.64,0.62,0.53,0.19,0.27,0.24]];
fn density(p:[f64;3],kind:u32,s:&ProceduralSettings,extent:V3,time:f64)->f64{
    let mut q=[0.;3];for a in 0..3{q[a]=p[a]-(s.wind[a] as f64*time/extent[a] as f64).rem_euclid(256.);}
    // Bounded lattice positions, continuous within the accepted time interval.
    let n1=noise(q.map(|x|x*6.),s.seed);
    let n2=noise(q.map(|x|x*15.+13.),s.seed.wrapping_add(17));
    let n3=noise(q.map(|x|x*33.-7.),s.seed.wrapping_add(31));
    let n=0.57*n1+0.29*n2+0.14*n3;
    let saturation=(s.humidity as f64-0.5)*0.45+(s.coverage as f64-0.5)*0.65;
    let mut envelope: f64;
    if kind==1 {
        let mut sdf: f64=-10.;for l in LOBES {let r=(0..3).map(|a|((p[a]-l[a])/l[a+3]).powi(2)).sum::<f64>().sqrt();sdf=sdf.max(1.-r);}
        envelope=smooth(-0.035,0.36,sdf+(n1-0.5)*0.60+(n2-0.5)*0.37+(n3-0.5)*0.22);
        envelope*=smooth(0.12,0.25,p[1])*(1.-smooth(0.88,1.,p[1]));
    }else{let radial=(((p[0]-0.5)/0.56).powi(2)+((p[2]-0.5)/0.56).powi(2)).sqrt();let mask=1.-smooth(0.58,1.12,radial+(n1-0.5)*0.4);envelope=(-p[1]*(3.5+4.*n2)).exp()*(1.-smooth(0.6,1.,p[1]))*mask*(0.35+0.85*n1+0.30*n2);}
    let edge=smooth(0.,0.10,p[0])*(1.-smooth(0.90,1.,p[0]))*smooth(0.,0.10,p[2])*(1.-smooth(0.90,1.,p[2]));
    let rho=(envelope*(0.52+0.95*n)+saturation-(0.20+(1.-n3)*s.erosion as f64)).clamp(0.,1.);
    rho*edge*if kind==1{envelope.sqrt()}else{envelope.clamp(0.,1.).sqrt()}
}
/// Writes x-fastest RGBA8 atlas, matching the solver's density/cap channel.
/// CPU procedural path only; no simulation velocity field or GPU claim.
pub fn procedural_atlas(config:&Config,kind:u32,settings:&ProceduralSettings,time:f64,out:&mut[u8])->Result<(),Error>{
    config.validate()?;
    if ![1,2].contains(&kind)||!time.is_finite()||!(0. ..=1e7).contains(&time)||[settings.coverage,settings.humidity,settings.erosion].iter().any(|x|!x.is_finite()||!(0. ..=1.).contains(x))||settings.wind.iter().any(|x|!x.is_finite()||x.abs()>100.) {return Err(Error::InvalidArgument("invalid procedural parameters"));}
    // Cap wind relative to extent to keep lattice coordinates within signed 32-bit range.
    let extent=config.extent();if (0..3).any(|a|settings.wind[a].abs()/extent[a]>100.){return Err(Error::InvalidArgument("procedural wind too large for volume"));}
    let len=config.voxel_count().checked_mul(4).ok_or(Error::Capacity)?;if out.len()<len{return Err(Error::BufferTooSmall);}
    let [nx,ny,nz]=config.cells;let mut i=0;for z in 0..nz{for y in 0..ny{for x in 0..nx{
        let p=[(x as f64+0.5)/nx as f64,(y as f64+0.5)/ny as f64,(z as f64+0.5)/nz as f64];
        let r=density(p,kind,settings,extent,time);out[i]=(r*255.).round() as u8;out[i+1]=0;out[i+2]=0;out[i+3]=255;i+=4;
    }}}Ok(())
}
#[cfg(test)]mod tests{
 use super::*;
 #[test]fn catalog_and_extent(){for id in 1..=8{let m=preset(id,1).unwrap();for q in [0,2]{let p=preset(id,q).unwrap();assert_eq!(p.preset.config.extent(),m.preset.config.extent());}}assert!(preset(99,1).is_err());}
 #[test]fn procedural_determinism_and_capacity(){let p=preset(3,0).unwrap().preset;let mut a=vec![0;p.config.voxel_count()*4];let mut b=a.clone();let s=p.procedural.unwrap();procedural_atlas(&p.config,p.kind,&s,0.,&mut a).unwrap();procedural_atlas(&p.config,p.kind,&s,0.,&mut b).unwrap();assert_eq!(a,b);assert!(a.chunks_exact(4).any(|v|v[0]>64));procedural_atlas(&p.config,p.kind,&s,20.,&mut b).unwrap();assert_ne!(a,b);assert!(procedural_atlas(&p.config,p.kind,&s,0.,&mut []).is_err());}
}

/// Game animation only: supplied progress drives ash/ember appearance, not combustion chemistry.
#[repr(C)]#[derive(Clone,Copy,Debug)]
pub struct EmberVisual {pub colour:V3,pub intensity:f32,pub heat:f32,pub ash_fraction:f32}
pub fn ember_visual(time:f64,progress:f32,lit:bool)->Result<EmberVisual,Error>{
 if !time.is_finite()||!(0. ..=1e7).contains(&time)||!progress.is_finite()||!(0. ..=1.).contains(&progress){return Err(Error::InvalidArgument("invalid ember animation time/progress"));}
 let heat=if lit{(0.72+0.08*(time*2.9).sin()+0.045*(time*7.3).sin()) as f32}else{0.};
 Ok(EmberVisual{colour:[1.,0.24+0.22*heat,0.035+0.05*heat],intensity:heat*3.2,heat,ash_fraction:progress})
}
