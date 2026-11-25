//! Optional stateless Fidelity C ABI. Explicit local metric extent and Float32 arrays.
//! The caller must provide disjoint, valid buffers for the duration of each call.
use super::*;
use vapor_core::fidelity as f;
#[repr(C)]#[derive(Clone,Copy)]pub struct CFidelityGrid {pub size:u32,pub version:u32,pub cells:[u32;3],pub reserved:u32,pub extent:[f64;3],pub density_cap:f64}
#[repr(C)]#[derive(Clone,Copy)]pub struct CFidelityDensity {pub size:u32,pub version:u32,pub kind:u32,pub seed:u32,pub coverage:f64,pub humidity:f64,pub erosion:f64,pub wind:[f64;3]}
#[repr(C)]#[derive(Clone,Copy)]pub struct CFidelityOptics {pub size:u32,pub version:u32,pub shadow_steps:u32,pub reserved:u32,pub colour:[f64;3],pub extinction:f64,pub anisotropy:f64,pub albedo:f64,pub emission:f64,pub thermal_fade:f64,pub ambient:f64,pub direction:[f64;3],pub radiance:[f64;3],pub sky:[f64;3],pub ground:[f64;3],pub multi_scatter:f64,pub light_scale:f64}
#[repr(C)]#[derive(Clone,Copy)]pub struct CFidelityCamera {pub size:u32,pub version:u32,pub width:u32,pub height:u32,pub steps:u32,pub dark:u32,pub eye:[f64;3],pub target:[f64;3],pub fov:f64,pub exposure:f64,pub jitter:f64}
fn grid(c:CFidelityGrid)->Result<f::FidelityGrid,Error>{if c.reserved!=0{return Err(Error::InvalidArgument("reserved must be zero"));}let g=f::FidelityGrid{cells:c.cells,extent:c.extent,density_cap:c.density_cap};g.count()?;Ok(g)}
fn kind(n:u32)->Result<f::VolumeKind,Error>{match n{1=>Ok(f::VolumeKind::Cloud),2=>Ok(f::VolumeKind::Fog),3=>Ok(f::VolumeKind::Dust),_=>Err(Error::InvalidArgument("unknown fidelity volume kind"))}}
fn aligned<T>(p:*const T)->bool{!p.is_null()&&(p as usize)%std::mem::align_of::<T>()==0}
unsafe fn input<'a,T>(p:*const T,n:usize,available:u32)->Result<&'a[T],Error>{if (available as usize)<n{return Err(Error::BufferTooSmall);}if !aligned(p){return Err(Error::InvalidArgument("invalid fidelity input pointer"));}Ok(slice::from_raw_parts(p,n))}
fn output<T>(p:*mut T,n:usize,available:u32)->Result<(),Error>{if (available as usize)<n{return Err(Error::BufferTooSmall);}if !aligned(p){return Err(Error::InvalidArgument("invalid fidelity output pointer"));}Ok(())}
#[no_mangle]pub unsafe extern "C" fn vapor_fidelity_generate_v1(g:*const CFidelityGrid,s:*const CFidelityDensity,time:f64,terrain:*const f32,terrain_elements:u32,density:*mut f32,temperature:*mut f32,elements:u32)->i32{guard(||{
    let g=grid(read_input(g)?)?;let s=read_input(s)?;let k=kind(s.kind)?;let n=g.count()?;output(density,n,elements)?;output(temperature,n,elements)?;
    let t=if terrain_elements==0{if !terrain.is_null(){return Err(Error::InvalidArgument("terrain pointer requires length"));}None}else{let count=g.cells[0] as usize*g.cells[2] as usize;if terrain_elements as usize!=count{return Err(Error::InvalidArgument("invalid terrain size"));}Some(input(terrain,count,terrain_elements)?)};
    let settings=f::DensitySettings{seed:s.seed,coverage:s.coverage,humidity:s.humidity,erosion:s.erosion,wind:s.wind};
    let field=f::FidelityGenerator::new(s.seed).generate(g,k,settings,time,t)?;
    ptr::copy_nonoverlapping(field.density.as_ptr(),density,n);ptr::copy_nonoverlapping(field.temperature.as_ptr(),temperature,n);Ok(())
})}
/// Caller-owned RGBA8 output; optional alpha buffer, optional scene arrays.
#[no_mangle]pub unsafe extern "C" fn vapor_fidelity_render_v1(g:*const CFidelityGrid,o:*const CFidelityOptics,c:*const CFidelityCamera,density:*const f32,temperature:*const f32,elements:u32,depth:*const f32,radiance:*const f32,scene_pixels:u32,rgba:*mut u8,bytes:u32,alpha:*mut f32,alpha_elements:u32)->i32{guard(||{
    let g=grid(read_input(g)?)?;let o=read_input(o)?;let c=read_input(c)?;if o.reserved!=0{return Err(Error::InvalidArgument("reserved must be zero"));}let dark=boolean(c.dark)?;
    if !(1..=1600).contains(&c.width)||!(1..=1600).contains(&c.height)||!(8..=512).contains(&c.steps){return Err(Error::InvalidArgument("invalid camera dimensions"));}let p=c.width as usize*c.height as usize;if p*c.steps as usize>180_000_000{return Err(Error::Capacity);}
    let n=g.count()?;output(rgba,p*4,bytes)?;if alpha_elements!=0{output(alpha,p,alpha_elements)?;}else if !alpha.is_null(){return Err(Error::InvalidArgument("alpha pointer requires length"));}
    let scene=if scene_pixels==0{if !depth.is_null()||!radiance.is_null(){return Err(Error::InvalidArgument("scene pointers require length"));}None}else{if scene_pixels as usize!=p{return Err(Error::InvalidArgument("invalid scene pixel count"));}Some(f::Scene{depth:input(depth,p,scene_pixels)?,radiance:input(radiance,p*3,scene_pixels*3)?})};
    let fields=f::FidelityFields{density:input(density,n,elements)?.to_vec(),temperature:input(temperature,n,elements)?.to_vec()};
    let material=f::OpticalMaterial{colour:o.colour,extinction:o.extinction,anisotropy:o.anisotropy,albedo:o.albedo,emission:o.emission,thermal_fade:o.thermal_fade,ambient:o.ambient};let lighting=f::FidelityLighting{direction:o.direction,radiance:o.radiance,sky:o.sky,ground:o.ground,multi_scatter:o.multi_scatter,shadow_steps:o.shadow_steps,light_scale:o.light_scale};
    let camera=f::FidelityCamera{eye:c.eye,target:c.target,width:c.width,height:c.height,steps:c.steps,fov:c.fov,exposure:c.exposure,jitter:c.jitter,dark};
    let image=f::FidelityRenderer::prepare(g,fields,material,lighting)?.render(camera,scene)?;
    ptr::copy_nonoverlapping(image.rgba.as_ptr(),rgba,p*4);if alpha_elements!=0{ptr::copy_nonoverlapping(image.alpha.as_ptr(),alpha,p);}Ok(())
})}
#[cfg(test)]mod tests{use super::*;#[test]fn fidelity_layout(){assert_eq!(size_of::<CFidelityGrid>(),56);assert_eq!(size_of::<CFidelityDensity>(),64);assert_eq!(size_of::<CFidelityOptics>(),200);assert_eq!(size_of::<CFidelityCamera>(),96);}}
