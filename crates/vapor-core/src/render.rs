//! Small deterministic offscreen ray marcher for previews/tests, not the game GPU renderer.
use crate::{Simulation,Error};
use crate::runtime::*;
#[derive(Clone,Debug)]
pub struct Camera {pub eye:[f32;3],pub target:[f32;3],pub up:[f32;3],pub vertical_fov_degrees:f32}
#[derive(Clone,Debug)]
pub struct RenderOptions {pub width:u32,pub height:u32,pub steps:u32,pub extinction:f32,pub colour:[f32;3]}
impl Default for RenderOptions{fn default()->Self{Self{width:320,height:240,steps:96,extinction:16.,colour:[0.85,0.9,0.95]}}}
pub fn render_rgba8(sim:&Simulation,camera:&Camera,o:&RenderOptions,out:&mut[u8])->Result<(),Error>{
 if o.width==0||o.height==0||o.width>4096||o.height>4096||!(8..=1024).contains(&o.steps)||!o.extinction.is_finite()||o.extinction<0.||!finite(o.colour)||o.colour.iter().any(|v|*v<0.||*v>1.){return Err(Error::InvalidArgument("invalid render options"));}
 if u64::from(o.width)*u64::from(o.height)*u64::from(o.steps)>256_000_000{return Err(Error::Capacity);}
 let pixels=(o.width as usize).checked_mul(o.height as usize).and_then(|n|n.checked_mul(4)).ok_or(Error::Capacity)?;
 if out.len()<pixels{return Err(Error::BufferTooSmall);}
 if !finite(camera.eye)||!finite(camera.target)||!finite(camera.up)||!camera.vertical_fov_degrees.is_finite()||!(1. ..170.).contains(&camera.vertical_fov_degrees){return Err(Error::InvalidArgument("invalid camera"));}
 let forward=sub(camera.target,camera.eye);let right=cross(forward,camera.up);if !len(forward).is_finite()||!len(right).is_finite()||len(forward)<1e-6||len(right)<1e-6{return Err(Error::InvalidArgument("degenerate camera basis"));}
 let forward=mul(forward,1./len(forward));let right=mul(right,1./len(right));let up=cross(right,forward);let half=(camera.vertical_fov_degrees.to_radians()*0.5).tan();let aspect=o.width as f32/o.height as f32;
 let cfg=sim.config();let min=cfg.origin;let max=add(min,cfg.extent());
 for y in 0..o.height{for x in 0..o.width{let u=(2.*(x as f32+0.5)/o.width as f32-1.)*aspect*half;let v=(1.-2.*(y as f32+0.5)/o.height as f32)*half;let d=add(forward,add(mul(right,u),mul(up,v)));let d=mul(d,1./len(d));let i=(x as usize+y as usize*o.width as usize)*4;out[i..i+4].fill(0);
  let mut lo=0f32;let mut hi=f32::INFINITY;for a in 0..3{if d[a].abs()<1e-8{if camera.eye[a]<min[a]||camera.eye[a]>max[a]{hi=-1.;break;}}else{let t0=(min[a]-camera.eye[a])/d[a];let t1=(max[a]-camera.eye[a])/d[a];lo=lo.max(t0.min(t1));hi=hi.min(t0.max(t1));}}
  if hi<=lo{continue;}let step=(hi-lo)/o.steps as f32;let mut trans=1f32;for s in 0..o.steps{let p=add(camera.eye,mul(d,lo+(s as f32+0.5)*step));let rho=sim.sample_density(p).max(0.);trans*=(-rho*o.extinction*step).exp();if trans<0.005{break;}}
  let alpha=1.-trans;for a in 0..3{out[i+a]=(o.colour[a]*alpha*255.).round() as u8;}out[i+3]=(alpha*255.).round() as u8;
 }}Ok(())
}
#[cfg(test)]mod tests{use super::*;use crate::Config;#[test]fn empty_render_transparent(){let sim=Simulation::new(Config{cells:[4;3],..Config::default()}).unwrap();let cam=Camera{eye:[0.05,0.05,-0.2],target:[0.05;3],up:[0.,1.,0.],vertical_fov_degrees:45.};let options=RenderOptions{width:8,height:8,..RenderOptions::default()};let mut out=vec![9;256];render_rgba8(&sim,&cam,&options,&mut out).unwrap();assert!(out.iter().all(|v|*v==0));}}

#[cfg(test)] mod safety_tests {
 use super::*;
 #[test] fn overflowing_camera_basis_is_rejected() {
   let sim=Simulation::new(Config{cells:[4;3],..Config::default()}).unwrap();
   let cam=Camera{eye:[f32::MAX,0.,0.],target:[-f32::MAX,0.,0.],up:[0.,1.,0.],vertical_fov_degrees:45.};
   let o=RenderOptions{width:8,height:8,..RenderOptions::default()};
   assert!(render_rgba8(&sim,&cam,&o,&mut [0;256]).is_err());
 }
 #[test] fn direct_render_has_work_budget() {
   let sim=Simulation::new(Config{cells:[4;3],..Config::default()}).unwrap();
   let cam=Camera{eye:[0.,0.,1.],target:[0.;3],up:[0.,1.,0.],vertical_fov_degrees:45.};
   let o=RenderOptions{width:4096,height:4096,steps:1024,..RenderOptions::default()};
   assert_eq!(render_rgba8(&sim,&cam,&o,&mut []),Err(Error::Capacity));
 }
}
