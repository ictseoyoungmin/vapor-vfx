use super::*;
use vapor_core::effects::{self as effect_core, Material, ProceduralSettings};
#[repr(C)]#[derive(Clone,Copy)]pub struct CProcedural {pub size:u32,pub version:u32,pub kind:u32,pub seed:u32,pub coverage:f32,pub humidity:f32,pub erosion:f32,pub wind:[f32;3]}
#[repr(C)]pub struct CEffectPreset {pub size:u32,pub version:u32,pub id:u32,pub kind:u32,pub config:CConfig,pub emitter:CEmitter,pub material:Material,pub procedural:CProcedural,pub ray_steps:u32,pub upload_hz:u32,pub ember:u32,pub profile_count:u32,pub duration:f32}
fn c_config(c:&Config)->CConfig{CConfig{size:size_of::<CConfig>() as u32,version:VERSION,nx:c.cells[0],ny:c.cells[1],nz:c.cells[2],cell_size:c.cell_size,origin:c.origin,fixed_dt:c.fixed_dt,max_substeps:c.max_substeps,pressure_iterations:c.pressure_iterations,sor_omega:c.sor_omega,density_decay:c.density_decay,cooling:c.cooling,buoyancy:c.buoyancy,density_weight:c.density_weight,drag:c.drag,vorticity:c.vorticity,wind:c.wind,max_velocity:c.max_velocity,density_cap:c.density_cap,boundary:c.boundary as u32}}
fn c_emitter(e:&Emitter)->CEmitter{CEmitter{size:size_of::<CEmitter>() as u32,version:VERSION,position:e.position,direction:e.direction,radius:e.radius,length:e.length,speed:e.speed,density_rate:e.density_rate,temperature:e.temperature,enabled:e.enabled as u32}}
#[no_mangle]pub unsafe extern "C" fn vapor_effect_preset_v1(id:u32,quality:u32,out:*mut CEffectPreset,bytes:u32)->i32{guard(||{
    let d=effect_core::preset(id,quality)?;let p=d.preset;let s=p.procedural.unwrap_or(ProceduralSettings{seed:0,coverage:0.,humidity:0.,erosion:0.,wind:[0.;3]});
    write_output(out,bytes,CEffectPreset{size:size_of::<CEffectPreset>() as u32,version:VERSION,id,kind:p.kind,config:c_config(&p.config),emitter:c_emitter(&p.emitter),material:p.material,procedural:CProcedural{size:size_of::<CProcedural>() as u32,version:VERSION,kind:p.kind,seed:s.seed,coverage:s.coverage,humidity:s.humidity,erosion:s.erosion,wind:s.wind},ray_steps:d.ray_steps,upload_hz:d.upload_hz,ember:p.ember as u32,profile_count:p.profile.len() as u32,duration:p.duration as f32})
})}
#[no_mangle]pub unsafe extern "C" fn vapor_effect_profile_v1(id:u32,out:*mut f64,elements:u32)->i32{guard(||{
    let p=effect_core::preset(id,1)?.preset;let n=p.profile.len()*4;
    if n==0{return Ok(());}if (elements as usize)<n{return Err(Error::BufferTooSmall);}if out.is_null()||(out as usize)%std::mem::align_of::<f64>()!=0{return Err(Error::InvalidArgument("invalid profile buffer"));}
    let dst=slice::from_raw_parts_mut(out,n);for (i,r) in p.profile.iter().enumerate(){dst[i*4..i*4+4].copy_from_slice(r);}Ok(())
})}
#[no_mangle]pub unsafe extern "C" fn vapor_procedural_atlas_v1(config:*const CConfig,settings:*const CProcedural,time:f64,out:*mut u8,bytes:u32)->i32{guard(||{
    let c=as_config(read_input(config)?)?;c.validate()?;let s=read_input(settings)?;let n=c.voxel_count()*4;
    if (bytes as usize)<n{return Err(Error::BufferTooSmall);}if out.is_null(){return Err(Error::InvalidArgument("null output"));}
    effect_core::procedural_atlas(&c,s.kind,&ProceduralSettings{seed:s.seed,coverage:s.coverage,humidity:s.humidity,erosion:s.erosion,wind:s.wind},time,slice::from_raw_parts_mut(out,n))
})}
#[cfg(test)]mod tests{use super::*;#[test]fn layouts(){assert_eq!(size_of::<CProcedural>(),40);assert_eq!(size_of::<Material>(),36);assert_eq!(size_of::<CEffectPreset>(),268);}}
#[no_mangle]pub unsafe extern "C" fn vapor_ember_visual_v1(time:f64,progress:f32,lit:u32,out:*mut effect_core::EmberVisual,bytes:u32)->i32{guard(||write_output(out,bytes,effect_core::ember_visual(time,progress,boolean(lit)?)?))}
