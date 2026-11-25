//! Versioned, caller-allocated C ABI. See include/vapor.h for the pointer contract.
#![allow(clippy::missing_safety_doc)]
use std::{cell::RefCell,collections::BTreeMap,mem::size_of,panic::{catch_unwind,AssertUnwindSafe},ptr,slice,sync::{Arc,Mutex,OnceLock,atomic::{AtomicUsize,Ordering}}};
use vapor_core::{Config,Boundary,Emitter,Obstacle,Shape,EmissionProfile,Field,Error};
use vapor_backend::{Engine as Simulation,BackendOptions,Mode};
use vapor_core::breath::{Point,Curve,BreathProfile};
const VERSION:u32=1;
const MEMORY_LIMIT:usize=512*1024*1024;
#[repr(C)]#[derive(Clone,Copy)]pub struct CConfig{pub size:u32,pub version:u32,pub nx:u32,pub ny:u32,pub nz:u32,pub cell_size:f32,pub origin:[f32;3],pub fixed_dt:f32,pub max_substeps:u32,pub pressure_iterations:u32,pub sor_omega:f32,pub density_decay:f32,pub cooling:f32,pub buoyancy:f32,pub density_weight:f32,pub drag:f32,pub vorticity:f32,pub wind:[f32;3],pub max_velocity:f32,pub density_cap:f32,pub boundary:u32}
#[repr(C)]#[derive(Clone,Copy)]pub struct CEmitter{pub size:u32,pub version:u32,pub position:[f32;3],pub direction:[f32;3],pub radius:f32,pub length:f32,pub speed:f32,pub density_rate:f32,pub temperature:f32,pub enabled:u32}
#[repr(C)]#[derive(Clone,Copy)]pub struct CObstacle{pub size:u32,pub version:u32,pub kind:u32,pub a:[f32;3],pub b:[f32;3],pub radius:f32,pub velocity:[f32;3],pub enabled:u32}
#[repr(C)]#[derive(Clone,Copy,Default)]pub struct CMetrics{pub size:u32,pub version:u32,pub ticks:u64,pub time:f64,pub density_integral:f64,pub max_density:f32,pub max_speed:f32,pub divergence_rms:f64,pub pressure_residual_rms:f64,pub centroid:[f64;3],pub non_finite:u32,pub reserved:u32,pub clamped_velocities:u64,pub dropped_seconds:f64,pub cpu_bytes:u64}
#[repr(C)]#[derive(Clone,Copy,Default)]pub struct CAdvance{pub size:u32,pub version:u32,pub steps:u32,pub reserved:u32,pub alpha:f64,pub dropped_seconds:f64,pub simulated_seconds:f64}
#[repr(C)]#[derive(Clone,Copy)]pub struct CRender{pub size:u32,pub version:u32,pub width:u32,pub height:u32,pub steps:u32,pub extinction:f32,pub colour:[f32;3],pub eye:[f32;3],pub target:[f32;3],pub up:[f32;3],pub vertical_fov_degrees:f32}
thread_local!{static LAST:RefCell<String>=const{RefCell::new(String::new())};}
fn status(e:Error)->i32{let code=match e{Error::InvalidConfig(_)|Error::InvalidArgument(_)=>-1,Error::InvalidHandle=>-2,Error::BufferTooSmall=>-3,Error::Capacity=>-4,Error::NonFiniteState=>-5,Error::Internal=>-6,Error::BackendUnavailable=>-7,Error::GpuFailure=>-8,Error::Unsupported=>-9};LAST.with(|s|*s.borrow_mut()=e.to_string());code}
fn guard(f:impl FnOnce()->Result<(),Error>)->i32{match catch_unwind(AssertUnwindSafe(f)){Ok(Ok(()))=>{LAST.with(|s|s.borrow_mut().clear());0},Ok(Err(e))=>status(e),Err(_)=>status(Error::Internal)}}
static LIVE_BYTES:AtomicUsize=AtomicUsize::new(0);
struct Tracked{sim:Mutex<Simulation>,bytes:usize}
impl Drop for Tracked{fn drop(&mut self){LIVE_BYTES.fetch_sub(self.bytes,Ordering::AcqRel);}}
#[derive(Default)]struct Registry{next:u32,entries:BTreeMap<u32,Arc<Tracked>>}
static SIMS:OnceLock<Mutex<Registry>>=OnceLock::new();
fn registry()->&'static Mutex<Registry>{SIMS.get_or_init(||Mutex::new(Registry{next:1,..Registry::default()}))}
fn lookup(h:u32)->Result<Arc<Tracked>,Error>{registry().lock().map_err(|_|Error::Internal)?.entries.get(&h).map(Arc::clone).ok_or(Error::InvalidHandle)}
fn with_sim<T>(h:u32,f:impl FnOnce(&mut Simulation)->Result<T,Error>)->Result<T,Error>{let sim=lookup(h)?;let mut sim=sim.sim.lock().map_err(|_|Error::Internal)?;f(&mut sim)}
unsafe fn read_input<T:Copy>(p:*const T)->Result<T,Error>{
 if p.is_null(){return Err(Error::InvalidArgument("null input"));}
 let raw=p.cast::<u32>();let size=ptr::read_unaligned(raw);let version=ptr::read_unaligned(raw.add(1));
 if size!=size_of::<T>() as u32||version!=VERSION{return Err(Error::InvalidArgument("ABI size/version mismatch"));}
 Ok(ptr::read_unaligned(p))
}
unsafe fn write_output<T>(p:*mut T,bytes:u32,value:T)->Result<(),Error>{if p.is_null(){return Err(Error::InvalidArgument("null output"));}if bytes<size_of::<T>() as u32{return Err(Error::BufferTooSmall);}ptr::write_unaligned(p,value);Ok(())}
fn as_config(c:CConfig)->Result<Config,Error>{Ok(Config{cells:[c.nx,c.ny,c.nz],cell_size:c.cell_size,origin:c.origin,fixed_dt:c.fixed_dt,max_substeps:c.max_substeps,pressure_iterations:c.pressure_iterations,sor_omega:c.sor_omega,density_decay:c.density_decay,cooling:c.cooling,buoyancy:c.buoyancy,density_weight:c.density_weight,drag:c.drag,vorticity:c.vorticity,wind:c.wind,max_velocity:c.max_velocity,density_cap:c.density_cap,boundary:match c.boundary{0=>Boundary::Open,1=>Boundary::Closed,_=>return Err(Error::InvalidArgument("unknown boundary"))}})}
fn field(v:u32)->Result<Field,Error>{match v{0=>Ok(Field::Density),1=>Ok(Field::Temperature),2=>Ok(Field::Pressure),3=>Ok(Field::Solid),4=>Ok(Field::Velocity),_=>Err(Error::InvalidArgument("unknown field"))}}
fn boolean(v:u32)->Result<bool,Error>{match v{0=>Ok(false),1=>Ok(true),_=>Err(Error::InvalidArgument("boolean must be 0 or 1"))}}
#[no_mangle]pub extern "C" fn vapor_abi_version_v1()->u32{VERSION}
#[no_mangle]pub unsafe extern "C" fn vapor_default_config_v1(out:*mut CConfig,bytes:u32)->i32{guard(||{let c=Config::default();write_output(out,bytes,CConfig{size:size_of::<CConfig>() as u32,version:VERSION,nx:c.cells[0],ny:c.cells[1],nz:c.cells[2],cell_size:c.cell_size,origin:c.origin,fixed_dt:c.fixed_dt,max_substeps:c.max_substeps,pressure_iterations:c.pressure_iterations,sor_omega:c.sor_omega,density_decay:c.density_decay,cooling:c.cooling,buoyancy:c.buoyancy,density_weight:c.density_weight,drag:c.drag,vorticity:c.vorticity,wind:c.wind,max_velocity:c.max_velocity,density_cap:c.density_cap,boundary:c.boundary as u32})})}
#[no_mangle]pub unsafe extern "C" fn vapor_default_emitter_v1(out:*mut CEmitter,bytes:u32)->i32{guard(||{let e=Emitter::default();write_output(out,bytes,CEmitter{size:size_of::<CEmitter>() as u32,version:VERSION,position:e.position,direction:e.direction,radius:e.radius,length:e.length,speed:e.speed,density_rate:e.density_rate,temperature:e.temperature,enabled:1})})}
/// Legacy creation shares the same RAII reservation and out-of-lock construction path.
#[no_mangle]
pub unsafe extern "C" fn vapor_create_v1(input:*const CConfig,out:*mut u32)->i32 {
    let options=CBackendOptions {
        size:size_of::<CBackendOptions>() as u32,version:VERSION,
        mode:Mode::Cpu as u32,detail_scale:1,flags:0,reserved:0,
        detail_turbulence:0.,detail_frequency:8.,
    };
    vapor_create_ex_v1(input,&options,out)
}
#[no_mangle]
pub extern "C" fn vapor_release_v1(h:u32)->i32 {
    guard(|| {
        let tracked={
            let mut r=registry().lock().map_err(|_|Error::Internal)?;
            r.entries.remove(&h).ok_or(Error::InvalidHandle)?
        };
        // GPU/resource destruction must never hold the process-wide registry mutex.
        drop(tracked);
        Ok(())
    })
}
#[no_mangle]pub extern "C" fn vapor_reset_v1(h:u32)->i32{guard(||with_sim(h,|s|s.reset()))}
#[no_mangle]pub extern "C" fn vapor_step_v1(h:u32,steps:u32)->i32{guard(||with_sim(h,|s|s.step_fixed(steps)))}
#[no_mangle]pub unsafe extern "C" fn vapor_advance_v1(h:u32,seconds:f64,out:*mut CAdvance,bytes:u32)->i32{guard(||{
 if out.is_null()||bytes<size_of::<CAdvance>() as u32{return Err(Error::BufferTooSmall);}
 with_sim(h,|s|{let r=s.advance(seconds)?;write_output(out,bytes,CAdvance{size:size_of::<CAdvance>() as u32,version:VERSION,steps:r.steps,reserved:0,alpha:r.alpha,dropped_seconds:r.dropped_seconds,simulated_seconds:r.simulated_seconds})})
})}
#[no_mangle]pub unsafe extern "C" fn vapor_set_emitter_v1(h:u32,id:u32,p:*const CEmitter)->i32{guard(||{let e=read_input(p)?;let e=Emitter{position:e.position,direction:e.direction,radius:e.radius,length:e.length,speed:e.speed,density_rate:e.density_rate,temperature:e.temperature,enabled:boolean(e.enabled)?};with_sim(h,|s|s.set_emitter(id,e))})}
#[no_mangle]pub extern "C" fn vapor_remove_emitter_v1(h:u32,id:u32)->i32{guard(||with_sim(h,|s|s.remove_emitter(id)))}
#[no_mangle]pub unsafe extern "C" fn vapor_set_obstacle_v1(h:u32,id:u32,p:*const CObstacle)->i32{guard(||{let o=read_input(p)?;let shape=match o.kind{0=>Shape::Capsule{a:o.a,b:o.b,radius:o.radius},1=>Shape::Box{min:o.a,max:o.b},_=>return Err(Error::InvalidArgument("unknown obstacle kind"))};let o=Obstacle{shape,velocity:o.velocity,enabled:boolean(o.enabled)?};with_sim(h,|s|s.set_obstacle(id,o))})}
#[no_mangle]pub extern "C" fn vapor_remove_obstacle_v1(h:u32,id:u32)->i32{guard(||with_sim(h,|s|s.remove_obstacle(id)))}
#[no_mangle]pub unsafe extern "C" fn vapor_set_profile_v1(h:u32,id:u32,rows:*const f64,count:u32,duration:f64,start_time:f64,repeat:u32)->i32{guard(||{
 if count==0{return with_sim(h,|s|s.set_profile(id,None));}
 if !(2..=64).contains(&count)||rows.is_null()||(rows as usize)%std::mem::align_of::<f64>()!=0{return Err(Error::InvalidArgument("invalid profile buffer"));}
 let values=slice::from_raw_parts(rows,count as usize*4);
 if values.chunks_exact(4).any(|r|r.iter().any(|v|!v.is_finite())||r[1]<0.||r[1]>16.||!(0. ..=1.).contains(&r[2])||r[3]<0.||r[3]>16.){return Err(Error::InvalidArgument("profile values out of range"));}
 let curve=|channel:usize|Curve::new(values.chunks_exact(4).map(|p|Point{x:p[0],y:p[channel]}).collect()).map_err(|_|Error::InvalidArgument("invalid curve control points"));
 let curve=BreathProfile::new(duration,curve(1)?,curve(2)?,curve(3)?).map_err(|_|Error::InvalidArgument("invalid profile duration"))?;
 let p=EmissionProfile{curve,start_time,repeat:boolean(repeat)?};with_sim(h,|s|s.set_profile(id,Some(p)))
})}
#[no_mangle]pub unsafe extern "C" fn vapor_metrics_v1(h:u32,out:*mut CMetrics,bytes:u32)->i32{guard(||with_sim(h,|s|{let m=s.metrics()?;write_output(out,bytes,CMetrics{size:size_of::<CMetrics>() as u32,version:VERSION,ticks:m.ticks,time:m.time,density_integral:m.density_integral,max_density:m.max_density,max_speed:m.max_speed,divergence_rms:m.divergence_rms,pressure_residual_rms:m.pressure_residual_rms,centroid:m.centroid,non_finite:m.non_finite,reserved:0,clamped_velocities:m.clamped_velocities,dropped_seconds:m.dropped_seconds,cpu_bytes:m.cpu_bytes})}))}
#[no_mangle]pub unsafe extern "C" fn vapor_field_len_v1(h:u32,f:u32,out:*mut u32)->i32{guard(||{let f=field(f)?;with_sim(h,|s|write_output(out,4,u32::try_from(s.field_len(f)).map_err(|_|Error::Capacity)?))})}
#[no_mangle]pub unsafe extern "C" fn vapor_copy_field_v1(h:u32,f:u32,out:*mut f32,elements:u32)->i32{guard(||{
 let f=field(f)?;if out.is_null()||(out as usize)%std::mem::align_of::<f32>()!=0{return Err(Error::InvalidArgument("null or unaligned field output"));}
 with_sim(h,|s|{let n=s.field_len(f);if (elements as usize)<n{return Err(Error::BufferTooSmall);}s.copy_field(f,slice::from_raw_parts_mut(out,n))})
})}
#[no_mangle]pub unsafe extern "C" fn vapor_copy_atlas_v1(h:u32,out:*mut u8,bytes:u32)->i32{guard(||{
 if out.is_null(){return Err(Error::InvalidArgument("null atlas output"));}with_sim(h,|s|{let n=s.info().render_cells.iter().map(|&n|n as usize).product::<usize>()*4;if (bytes as usize)<n{return Err(Error::BufferTooSmall);}s.copy_atlas_rgba8(slice::from_raw_parts_mut(out,n))})
})}
#[repr(C)]#[derive(Clone,Copy)]
pub struct CAtlasTicket {pub size:u32,pub version:u32,pub id:u64,pub ticks:u64,pub bytes:u32,pub reserved:u32}
#[no_mangle]pub unsafe extern "C" fn vapor_begin_atlas_v1(h:u32,out:*mut CAtlasTicket,bytes:u32)->i32{guard(||{
 if out.is_null(){return Err(Error::InvalidArgument("null ticket output"));}
 if bytes<size_of::<CAtlasTicket>() as u32{return Err(Error::BufferTooSmall);}
 with_sim(h,|s|{let t=s.begin_atlas()?;
     write_output(out,bytes,CAtlasTicket{size:size_of::<CAtlasTicket>() as u32,version:VERSION,
         id:t.map_or(0,|t|t.id),ticks:t.map_or(0,|t|t.ticks),bytes:t.map_or(0,|t|t.bytes as u32),reserved:0})})
})}
#[no_mangle]pub unsafe extern "C" fn vapor_poll_atlas_v1(h:u32,id:u64,out:*mut u8,bytes:u32,ready:*mut u32)->i32{guard(||{
 if out.is_null()||ready.is_null(){return Err(Error::InvalidArgument("null atlas or ready output"));}
 ptr::write_unaligned(ready,0);
 with_sim(h,|s|{
     let n=s.info().render_cells.iter().map(|&n|n as usize).product::<usize>()*4;
     if (bytes as usize)<n{return Err(Error::BufferTooSmall);}
     let done=s.poll_atlas(id,slice::from_raw_parts_mut(out,n))?;
     ptr::write_unaligned(ready,u32::from(done));Ok(())
 })
})}
#[no_mangle]pub extern "C" fn vapor_cancel_atlas_v1(h:u32,id:u64)->i32{guard(||with_sim(h,|s|s.cancel_atlas(id)))}
#[no_mangle]pub unsafe extern "C" fn vapor_render_v1(h:u32,p:*const CRender,out:*mut u8,bytes:u32)->i32{guard(||{
 let r=read_input(p)?;let n=(r.width as usize).checked_mul(r.height as usize).and_then(|x|x.checked_mul(4)).ok_or(Error::Capacity)?;
 if out.is_null()||n>64*1024*1024{return Err(Error::InvalidArgument("invalid render output"));}if (bytes as usize)<n{return Err(Error::BufferTooSmall);}
 if (r.width as u64)*(r.height as u64)*(r.steps as u64)>256_000_000{return Err(Error::Capacity);}
 let camera=vapor_core::render::Camera{eye:r.eye,target:r.target,up:r.up,vertical_fov_degrees:r.vertical_fov_degrees};let options=vapor_core::render::RenderOptions{width:r.width,height:r.height,steps:r.steps,extinction:r.extinction,colour:r.colour};
 with_sim(h,|s|s.render(&camera,&options,slice::from_raw_parts_mut(out,n)))
})}
#[no_mangle]pub unsafe extern "C" fn vapor_last_error_v1(out:*mut u8,capacity:u32)->u32{
 LAST.with(|s|{let text=s.borrow();let bytes=text.as_bytes();if !out.is_null()&&capacity>0{let n=bytes.len().min(capacity as usize-1);ptr::copy_nonoverlapping(bytes.as_ptr(),out,n);*out.add(n)=0;}bytes.len() as u32})
}
#[derive(Default)]struct Scratch{blocks:BTreeMap<usize,Box<[u64]>>,bytes:usize}
static SCRATCH:OnceLock<Mutex<Scratch>>=OnceLock::new();
#[no_mangle]pub extern "C" fn vapor_alloc_v1(bytes:u32)->*mut u8{
 let result=catch_unwind(AssertUnwindSafe(||->Result<*mut u8,Error>{if bytes==0||bytes>64*1024*1024{return Err(Error::Capacity);}let words=(bytes as usize).div_ceil(8);let total=words*8;
 let mut r=SCRATCH.get_or_init(||Mutex::new(Scratch::default())).lock().map_err(|_|Error::Internal)?;if r.bytes+total>128*1024*1024{return Err(Error::Capacity);}
 let mut v=Vec::<u64>::new();v.try_reserve_exact(words).map_err(|_|Error::Capacity)?;v.resize(words,0);let mut data=v.into_boxed_slice();let p=data.as_mut_ptr() as *mut u8;r.blocks.insert(p as usize,data);r.bytes+=total;Ok(p)}));
 match result{Ok(Ok(p))=>p,Ok(Err(e))=>{status(e);ptr::null_mut()},Err(_)=>{status(Error::Internal);ptr::null_mut()}}
}
#[no_mangle]pub extern "C" fn vapor_free_v1(p:*mut u8)->i32{guard(||{let mut r=SCRATCH.get_or_init(||Mutex::new(Scratch::default())).lock().map_err(|_|Error::Internal)?;let b=r.blocks.remove(&(p as usize)).ok_or(Error::InvalidHandle)?;r.bytes-=b.len()*8;Ok(())})}

#[cfg(test)]mod tests{
 use super::*;
 fn config()->CConfig{let mut out=std::mem::MaybeUninit::uninit();unsafe{assert_eq!(vapor_default_config_v1(out.as_mut_ptr(),size_of::<CConfig>() as u32),0);let mut c=out.assume_init();c.nx=6;c.ny=6;c.nz=6;c}}
 #[test]fn layout_matches_c(){assert_eq!(size_of::<CConfig>(),100);assert_eq!(size_of::<CEmitter>(),56);assert_eq!(size_of::<CObstacle>(),56);assert_eq!(size_of::<CMetrics>(),112);assert_eq!(size_of::<CAdvance>(),40);assert_eq!(size_of::<CRender>(),76);}
 #[test]fn lifecycle_and_reject_stale_handle(){let cfg=config();let mut h=0;unsafe{assert_eq!(vapor_create_v1(&cfg,&mut h),0);}assert_ne!(h,0);assert_eq!(vapor_step_v1(h,1),0);assert_eq!(vapor_release_v1(h),0);assert_eq!(vapor_step_v1(h,1),-2);assert_eq!(vapor_release_v1(h),-2);}
 #[test]fn bad_buffers_and_version(){unsafe{assert_eq!(vapor_create_v1(ptr::null(),ptr::null_mut()),-1);let mut c=config();c.version=999;let mut h=45;assert_eq!(vapor_create_v1(&c,&mut h),-1);assert_eq!(h,0);}}
 #[test]fn safe_scratch(){let p=vapor_alloc_v1(64);assert!(!p.is_null());assert_eq!((p as usize)%8,0);assert_eq!(vapor_free_v1(p),0);assert_eq!(vapor_free_v1(p),-2);assert!(vapor_alloc_v1(u32::MAX).is_null());}
}

/// ABI extensions are additive: legacy create remains CPU and old struct sizes do not change.
#[repr(C)] #[derive(Clone,Copy)]
pub struct CBackendOptions {
    pub size:u32,pub version:u32,pub mode:u32,pub detail_scale:u32,pub flags:u32,pub reserved:u32,
    pub detail_turbulence:f32,pub detail_frequency:f32,
}
#[repr(C)] #[derive(Clone,Copy)]
pub struct CBackendInfo {
    pub size:u32,pub version:u32,pub requested:u32,pub active:u32,pub detail_scale:u32,pub flags:u32,
    pub render_cells:[u32;3],pub reserved:u32,pub cpu_bytes:u64,pub gpu_bytes:u64,pub hybrid_upload_bytes:u64,
}
#[no_mangle] pub unsafe extern "C" fn vapor_create_ex_v1(input:*const CConfig,backend:*const CBackendOptions,out:*mut u32)->i32 {
    guard(||{
        if out.is_null(){return Err(Error::InvalidArgument("null handle output"));}ptr::write_unaligned(out,0);
        let cfg=as_config(read_input(input)?)?;let o=read_input(backend)?;
        if o.reserved!=0{return Err(Error::InvalidArgument("reserved backend field must be zero"));}
        let options=BackendOptions{mode:Mode::try_from(o.mode)?,detail_scale:o.detail_scale,flags:o.flags,detail_turbulence:o.detail_turbulence,detail_frequency:o.detail_frequency};
        let bytes=Simulation::reservation_bytes(&cfg,&options)?;
        // Reserve under the registry lock, but NEVER hold it during GPU/device creation.
        let h={let mut r=registry().lock().map_err(|_|Error::Internal)?;
            if r.entries.len()>=64||r.next==u32::MAX||LIVE_BYTES.load(Ordering::Acquire).checked_add(bytes).ok_or(Error::Capacity)?>MEMORY_LIMIT{return Err(Error::Capacity);}
            let h=r.next;r.next+=1;LIVE_BYTES.fetch_add(bytes,Ordering::AcqRel);h
        };
        struct Reservation(usize);
        impl Drop for Reservation{fn drop(&mut self){LIVE_BYTES.fetch_sub(self.0,Ordering::AcqRel);}}
        let reservation=Reservation(bytes);
        let sim=Simulation::with_options(cfg,options)?;
        let mut r=registry().lock().map_err(|_|Error::Internal)?;
        if r.entries.len()>=64{return Err(Error::Capacity);}
        // Transfer the exact reservation to Tracked; both error and panic paths are RAII-safe.
        let tracked=Arc::new(Tracked{sim:Mutex::new(sim),bytes});std::mem::forget(reservation);
        r.entries.insert(h,tracked);ptr::write_unaligned(out,h);Ok(())
    })
}
#[no_mangle] pub unsafe extern "C" fn vapor_backend_info_v1(h:u32,out:*mut CBackendInfo,bytes:u32)->i32 {
    guard(||with_sim(h,|s|{let i=s.info();write_output(out,bytes,CBackendInfo{
        size:size_of::<CBackendInfo>() as u32,version:VERSION,requested:i.requested as u32,active:i.active as u32,detail_scale:i.detail_scale,flags:i.flags,
        render_cells:i.render_cells,reserved:0,cpu_bytes:i.cpu_bytes,gpu_bytes:i.gpu_bytes,hybrid_upload_bytes:i.hybrid_upload_bytes,
    })}))
}
#[no_mangle] pub unsafe extern "C" fn vapor_copy_mac_v1(h:u32,out:*mut f32,elements:u32)->i32 {
    guard(||{
        if out.is_null()||(out as usize)%std::mem::align_of::<f32>()!=0{return Err(Error::InvalidArgument("invalid MAC output pointer"));}
        with_sim(h,|s|{let n=s.config().padded_len()?*8;if (elements as usize)<n{return Err(Error::BufferTooSmall);}s.copy_mac(slice::from_raw_parts_mut(out,n))})
    })
}

mod effects;

mod fidelity;
