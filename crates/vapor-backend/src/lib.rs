//! Runtime selection with explicit semantics. `Hybrid` is a one-way coarse CPU MAC
//! solve feeding a fine GPU passive-scalar solve, not a mid-frame CPU/GPU fallback.
pub mod protocol;
#[cfg(all(feature="gpu",not(target_arch="wasm32")))]
mod native;
use vapor_core::{AdvanceReport, Config, Emitter, EmissionProfile, Error, Field, Metrics, Obstacle, Simulation};
use vapor_core::runtime::{Clock, MAX_STEPS_PER_CALL};

#[derive(Clone,Copy,Debug,PartialEq,Eq)]
#[repr(u32)]
pub enum Mode { Auto=0, Cpu=1, Gpu=2, Hybrid=3 }
impl TryFrom<u32> for Mode {
    type Error=Error;
    fn try_from(v:u32)->Result<Self,Error>{match v{0=>Ok(Self::Auto),1=>Ok(Self::Cpu),2=>Ok(Self::Gpu),3=>Ok(Self::Hybrid),_=>Err(Error::InvalidArgument("unknown backend mode"))}}
}
pub const ALLOW_CPU_FALLBACK:u32=1;
pub const ALLOW_SOFTWARE_GPU:u32=2;
#[derive(Clone,Copy,Debug)]
pub struct BackendOptions {
    pub mode:Mode, pub detail_scale:u32, pub flags:u32,
    /// Fine kinematic curl amplitude (m/s), base wave number (rad/m). Zero amplitude disables it.
    pub detail_turbulence:f32, pub detail_frequency:f32,
}
impl Default for BackendOptions {
    fn default()->Self{Self{mode:Mode::Cpu,detail_scale:1,flags:0,detail_turbulence:0.,detail_frequency:8.}}
}
impl BackendOptions {
    pub fn validate(&self,cfg:&Config)->Result<(),Error>{
        cfg.validate()?;
        if !(1..=4).contains(&self.detail_scale)||self.flags & !3 != 0 {return Err(Error::InvalidArgument("invalid backend flags/detail scale"));}
        if !self.detail_turbulence.is_finite()||!(0. ..=2.).contains(&self.detail_turbulence)||
           !self.detail_frequency.is_finite()||!(0.1..=100.).contains(&self.detail_frequency) {
            return Err(Error::InvalidArgument("invalid detail turbulence/frequency"));
        }
        if self.mode==Mode::Cpu&&(self.detail_scale!=1||self.detail_turbulence!=0.) {
            return Err(Error::InvalidArgument("CPU mode requires detail_scale=1 and detail_turbulence=0"));
        }
        if matches!(self.mode,Mode::Gpu|Mode::Auto)&&self.detail_scale==1&&self.detail_turbulence!=0. {
            return Err(Error::InvalidArgument("GPU detail turbulence requires detail_scale>1"));
        }
        if cfg.voxel_count().checked_mul((self.detail_scale as usize).pow(3)).ok_or(Error::Capacity)?>2_097_152 {
            return Err(Error::Capacity);
        }
        let fine_cfl=3f32.sqrt()*(cfg.max_velocity+2.*self.detail_turbulence)*cfg.fixed_dt/cfg.cell_size*self.detail_scale as f32;
        if fine_cfl>128. {return Err(Error::InvalidArgument("detail transport exceeds collision traversal budget"));}
        Ok(())
    }
}
#[derive(Clone,Copy,Debug)]
pub struct BackendInfo {
    pub requested:Mode,pub active:Mode,pub detail_scale:u32,pub flags:u32,pub render_cells:[u32;3],
    pub cpu_bytes:u64,pub gpu_bytes:u64,pub hybrid_upload_bytes:u64,
}
// Info bits: CPU compute=1, GPU compute=2, one-way hybrid=4, init fallback=8,
// blocking native readback=16, software GPU=32, ticketed atlas=64. Rendering alone never sets GPU compute.
enum Kind {
    Cpu(Simulation),
    #[cfg(all(feature="gpu",not(target_arch="wasm32")))]
    Gpu(native::Gpu),
    #[cfg(all(feature="gpu",not(target_arch="wasm32")))]
    Hybrid {cpu:Simulation,gpu:native::Gpu},
}
/// Snapshot provenance. IDs are monotonic within an engine, including across reset.
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub struct AtlasTicket {pub id:u64,pub ticks:u64,pub bytes:usize}
pub struct Engine {kind:Kind,cfg:Config,options:BackendOptions,clock:Clock,fallback:bool,failed:Option<Error>,
    next_atlas_id:u64,pending_atlas:Option<AtlasTicket>,cpu_atlas:Vec<u8>}
impl Engine {
    pub fn reservation_bytes(cfg:&Config,options:&BackendOptions)->Result<usize,Error>{
        options.validate(cfg)?;
        if options.mode==Mode::Cpu{return cfg.estimated_cpu_bytes()?.checked_add(cfg.voxel_count()*4).ok_or(Error::Capacity);}
        let n=cfg.padded_len()?;let fine=cfg.voxel_count()*(options.detail_scale as usize).pow(3);
        // Conservative core arrays, upload buffers, diagnostics, sync and async staging; not process RSS.
        n.checked_mul(336).and_then(|a|fine.checked_mul(64).and_then(|b|a.checked_add(b+8192))).ok_or(Error::Capacity)
    }
    pub fn new(cfg:Config)->Result<Self,Error>{Self::with_options(cfg,BackendOptions::default())}
    pub fn with_options(cfg:Config,options:BackendOptions)->Result<Self,Error>{
        options.validate(&cfg)?;let mut fallback=false;
        let kind=if options.mode==Mode::Cpu {Kind::Cpu(Simulation::new(cfg.clone())?)} else {
            #[cfg(all(feature="gpu",not(target_arch="wasm32")))]
            let gpu=native::Gpu::new(cfg.clone(),options,options.mode==Mode::Hybrid);
            #[cfg(not(all(feature="gpu",not(target_arch="wasm32"))))]
            let gpu:Result<(),Error>=Err(Error::BackendUnavailable);
            match gpu {
                #[cfg(all(feature="gpu",not(target_arch="wasm32")))]
                Ok(gpu)=>if options.mode==Mode::Hybrid {Kind::Hybrid{cpu:Simulation::new(cfg.clone())?,gpu}}else{Kind::Gpu(gpu)},
                #[cfg(not(all(feature="gpu",not(target_arch="wasm32"))))]
                Ok(())=>return Err(Error::Internal),
                Err(Error::BackendUnavailable) if options.mode==Mode::Auto && options.flags&ALLOW_CPU_FALLBACK!=0 => {
                    fallback=true;Kind::Cpu(Simulation::new(cfg.clone())?)
                },
                Err(e)=>return Err(e),
            }
        };
        Ok(Self{kind,cfg,options,clock:Clock::default(),fallback,failed:None,next_atlas_id:1,pending_atlas:None,cpu_atlas:Vec::new()})
    }
    fn check_state(&self)->Result<(),Error>{
        if let Some(error)=self.failed {return Err(error);}
        match &self.kind {
            Kind::Cpu(_)=>Ok(()),
            #[cfg(all(feature="gpu",not(target_arch="wasm32")))]
            Kind::Gpu(g)=>g.check(),
            #[cfg(all(feature="gpu",not(target_arch="wasm32")))]
            Kind::Hybrid{gpu,..}=>gpu.check(),
        }
    }
    pub fn config(&self)->&Config{&self.cfg}
    pub fn info(&self)->BackendInfo{
        let (active,mut flags,scale,cpu_bytes,gpu_bytes,upload)=match &self.kind{
            Kind::Cpu(s)=>(Mode::Cpu,1,1,(s.config().estimated_cpu_bytes().unwrap_or(0)+self.cpu_atlas.capacity()) as u64,0,0),
            #[cfg(all(feature="gpu",not(target_arch="wasm32")))]
            Kind::Gpu(g)=>(Mode::Gpu,2|16|if g.software{32}else{0},self.options.detail_scale,0,g.allocated_bytes,0),
            #[cfg(all(feature="gpu",not(target_arch="wasm32")))]
            Kind::Hybrid{cpu,gpu}=>(Mode::Hybrid,1|2|4|16|if gpu.software{32}else{0},self.options.detail_scale,
                cpu.config().estimated_cpu_bytes().unwrap_or(0) as u64,gpu.allocated_bytes,(self.cfg.padded_len().unwrap_or(0)*32) as u64),
        };
        if self.fallback{flags|=8;}
        flags|=64; // additive ticketed atlas API; CPU is ready immediately
        BackendInfo{requested:self.options.mode,active,detail_scale:scale,flags,render_cells:self.cfg.cells.map(|n|n*scale),cpu_bytes,gpu_bytes,hybrid_upload_bytes:upload}
    }
    pub fn time(&self)->f64{self.clock.ticks as f64*self.cfg.fixed_dt as f64}
    pub fn reset(&mut self)->Result<(),Error>{
        self.clear_atlas();
        match &mut self.kind{
            Kind::Cpu(s)=>s.reset(),
            #[cfg(all(feature="gpu",not(target_arch="wasm32")))]
            Kind::Gpu(g)=>g.reset()?,
            #[cfg(all(feature="gpu",not(target_arch="wasm32")))]
            Kind::Hybrid{cpu,gpu}=>{gpu.reset()?;cpu.reset();},
        }
        self.clock=Clock::default();self.failed=None;Ok(())
    }
    pub fn step_fixed(&mut self,count:u32)->Result<(),Error>{
        if count>MAX_STEPS_PER_CALL{return Err(Error::InvalidArgument("too many steps in one call"));}
        self.check_state()?;
        for _ in 0..count{
            let next=self.clock.ticks.checked_add(1).ok_or(Error::Capacity)?;
            let time=self.time();
            let result=match &mut self.kind{
                Kind::Cpu(s)=>s.step_fixed(1),
                #[cfg(all(feature="gpu",not(target_arch="wasm32")))]
                Kind::Gpu(g)=>g.step(time,None),
                #[cfg(all(feature="gpu",not(target_arch="wasm32")))]
                Kind::Hybrid{cpu,gpu}=>(||{
                    gpu.check()?;
                    // Prevalidate the entire control packet before either side changes state.
                    protocol::controls(&self.cfg,cpu.scene(),time)?;
                    cpu.step_fixed(1)?;
                    gpu.step(time,Some(cpu.mac_cells()))
                })(),
            };
            if let Err(e)=result{if !matches!(e,Error::InvalidArgument(_)|Error::InvalidConfig(_)){self.failed=Some(e);}return Err(e);}self.clock.ticks=next;
        }Ok(())
    }
    pub fn advance(&mut self,elapsed:f64)->Result<AdvanceReport,Error>{
        let (steps,residual,dropped)=self.clock.plan(elapsed,&self.cfg)?;
        self.step_fixed(steps)?;self.clock.accumulator=residual;self.clock.dropped_total+=dropped;
        Ok(AdvanceReport{steps,alpha:residual/self.cfg.fixed_dt as f64,dropped_seconds:dropped,simulated_seconds:self.time()})
    }
    pub fn set_emitter(&mut self,id:u32,e:Emitter)->Result<(),Error>{
        match &mut self.kind{
            Kind::Cpu(s)=>s.set_emitter(id,e),
            #[cfg(all(feature="gpu",not(target_arch="wasm32")))]
            Kind::Gpu(g)=>g.scene.set_emitter(&self.cfg,id,e),
            #[cfg(all(feature="gpu",not(target_arch="wasm32")))]
            Kind::Hybrid{cpu,gpu}=>{cpu.set_emitter(id,e.clone())?;gpu.scene.set_emitter(&self.cfg,id,e)},
        }
    }
    pub fn remove_emitter(&mut self,id:u32)->Result<(),Error>{match &mut self.kind{
        Kind::Cpu(s)=>s.remove_emitter(id),
        #[cfg(all(feature="gpu",not(target_arch="wasm32")))] Kind::Gpu(g)=>g.scene.remove_emitter(id),
        #[cfg(all(feature="gpu",not(target_arch="wasm32")))] Kind::Hybrid{cpu,gpu}=>{cpu.remove_emitter(id)?;gpu.scene.remove_emitter(id)},
    }}
    pub fn set_profile(&mut self,id:u32,p:Option<EmissionProfile>)->Result<(),Error>{match &mut self.kind{
        Kind::Cpu(s)=>s.set_profile(id,p),
        #[cfg(all(feature="gpu",not(target_arch="wasm32")))] Kind::Gpu(g)=>g.scene.set_profile(id,p),
        #[cfg(all(feature="gpu",not(target_arch="wasm32")))] Kind::Hybrid{cpu,gpu}=>{cpu.set_profile(id,p.clone())?;gpu.scene.set_profile(id,p)},
    }}
    pub fn set_obstacle(&mut self,id:u32,o:Obstacle)->Result<(),Error>{match &mut self.kind{
        Kind::Cpu(s)=>s.set_obstacle(id,o),
        #[cfg(all(feature="gpu",not(target_arch="wasm32")))] Kind::Gpu(g)=>g.scene.set_obstacle(&self.cfg,id,o),
        #[cfg(all(feature="gpu",not(target_arch="wasm32")))] Kind::Hybrid{cpu,gpu}=>{cpu.set_obstacle(id,o.clone())?;gpu.scene.set_obstacle(&self.cfg,id,o)},
    }}
    pub fn remove_obstacle(&mut self,id:u32)->Result<(),Error>{match &mut self.kind{
        Kind::Cpu(s)=>s.remove_obstacle(id),
        #[cfg(all(feature="gpu",not(target_arch="wasm32")))] Kind::Gpu(g)=>g.scene.remove_obstacle(id),
        #[cfg(all(feature="gpu",not(target_arch="wasm32")))] Kind::Hybrid{cpu,gpu}=>{cpu.remove_obstacle(id)?;gpu.scene.remove_obstacle(id)},
    }}
    // Field/metrics APIs always describe the BASE physical grid, including hybrid.
    // Only atlas/render_cells use the optional finer passive-scalar grid.
    pub fn field_len(&self,f:Field)->usize{self.cfg.voxel_count()*f.channels()}
    pub fn copy_field(&self,f:Field,out:&mut[f32])->Result<(),Error>{self.check_state()?;match &self.kind{
        Kind::Cpu(s)=>s.copy_field(f,out),
        #[cfg(all(feature="gpu",not(target_arch="wasm32")))] Kind::Gpu(g)=>g.snapshot(self.clock.clone())?.copy_field(f,out),
        #[cfg(all(feature="gpu",not(target_arch="wasm32")))] Kind::Hybrid{cpu,..}=>cpu.copy_field(f,out),
    }}
    pub fn copy_mac(&self,out:&mut[f32])->Result<(),Error>{
        self.check_state()?;
        let needed=self.cfg.padded_len()?*8;if out.len()<needed{return Err(Error::BufferTooSmall);}
        let copy=|cells:&[vapor_core::solver::Cell],out:&mut[f32]|{for(c,o)in cells.iter().zip(out.chunks_exact_mut(8)){o[..4].copy_from_slice(&c.v);o[4..].copy_from_slice(&c.s);}};
        match &self.kind{
            Kind::Cpu(s)=>copy(s.mac_cells(),out),
            #[cfg(all(feature="gpu",not(target_arch="wasm32")))] Kind::Gpu(g)=>copy(g.snapshot(self.clock.clone())?.mac_cells(),out),
            #[cfg(all(feature="gpu",not(target_arch="wasm32")))] Kind::Hybrid{cpu,..}=>copy(cpu.mac_cells(),out),
        }Ok(())
    }
    pub fn copy_atlas_rgba8(&self,out:&mut[u8])->Result<(),Error>{self.check_state()?;match &self.kind{
        Kind::Cpu(s)=>s.copy_atlas_rgba8(out),
        #[cfg(all(feature="gpu",not(target_arch="wasm32")))] Kind::Gpu(g)=>g.copy_atlas(out),
        #[cfg(all(feature="gpu",not(target_arch="wasm32")))] Kind::Hybrid{gpu,..}=>gpu.copy_atlas(out),
    }}
    /// One bounded outstanding atlas request per instance. None = backpressure, NOT failure.
    /// CPU packs immediately; GPU/Hybrid enqueue copy+map without waiting for completion.
    pub fn begin_atlas(&mut self)->Result<Option<AtlasTicket>,Error>{
        self.check_state()?;
        if self.pending_atlas.is_some(){return Ok(None);}
        let next=self.next_atlas_id.checked_add(1).ok_or(Error::Capacity)?;
        let bytes=self.info().render_cells.iter().map(|&n|n as usize).product::<usize>()*4;
        let ticket=AtlasTicket{id:self.next_atlas_id,ticks:self.clock.ticks,bytes};
        match &mut self.kind{
            Kind::Cpu(s)=>{
                if self.cpu_atlas.len()!=bytes{
                    self.cpu_atlas.try_reserve_exact(bytes.saturating_sub(self.cpu_atlas.len())).map_err(|_|Error::Capacity)?;
                    self.cpu_atlas.resize(bytes,0);
                }
                s.copy_atlas_rgba8(&mut self.cpu_atlas)?;
            },
            #[cfg(all(feature="gpu",not(target_arch="wasm32")))]
            Kind::Gpu(g)=>g.begin_atlas()?,
            #[cfg(all(feature="gpu",not(target_arch="wasm32")))]
            Kind::Hybrid{gpu,..}=>gpu.begin_atlas()?,
        }
        self.next_atlas_id=next;self.pending_atlas=Some(ticket);Ok(Some(ticket))
    }
    fn clear_atlas(&mut self){
        self.pending_atlas=None;
        match &mut self.kind{
            Kind::Cpu(_)=>{},
            #[cfg(all(feature="gpu",not(target_arch="wasm32")))]
            Kind::Gpu(g)=>g.cancel_atlas(),
            #[cfg(all(feature="gpu",not(target_arch="wasm32")))]
            Kind::Hybrid{gpu,..}=>gpu.cancel_atlas(),
        }
    }
    pub fn cancel_atlas(&mut self,id:u64)->Result<(),Error>{
        if self.pending_atlas.map(|t|t.id)!=Some(id){return Err(Error::InvalidHandle);}
        self.clear_atlas();Ok(())
    }
    /// Pending leaves caller output untouched; Ready copies once and consumes the ticket.
    /// BufferTooSmall is retryable. Terminal device/numerical failures consume the request.
    pub fn poll_atlas(&mut self,id:u64,out:&mut[u8])->Result<bool,Error>{
        let ticket=self.pending_atlas.filter(|t|t.id==id).ok_or(Error::InvalidHandle)?;
        if out.len()<ticket.bytes{return Err(Error::BufferTooSmall);}
        if let Err(e)=self.check_state(){self.clear_atlas();return Err(e);}
        let result=match &mut self.kind{
            Kind::Cpu(_)=>{out[..ticket.bytes].copy_from_slice(&self.cpu_atlas);Ok(true)},
            #[cfg(all(feature="gpu",not(target_arch="wasm32")))]
            Kind::Gpu(g)=>g.poll_atlas(out),
            #[cfg(all(feature="gpu",not(target_arch="wasm32")))]
            Kind::Hybrid{gpu,..}=>gpu.poll_atlas(out),
        };
        if !matches!(result,Ok(false)){self.clear_atlas();}
        result
    }
    pub fn metrics(&self)->Result<Metrics,Error>{
        self.check_state()?;
        let mut m=match &self.kind{
            Kind::Cpu(s)=>s.metrics(),
            #[cfg(all(feature="gpu",not(target_arch="wasm32")))] Kind::Gpu(g)=>g.snapshot(self.clock.clone())?.metrics(),
            #[cfg(all(feature="gpu",not(target_arch="wasm32")))] Kind::Hybrid{cpu,..}=>cpu.metrics(),
        };m.dropped_seconds=self.clock.dropped_total;Ok(m)
    }
    pub fn render(&self,c:&vapor_core::render::Camera,o:&vapor_core::render::RenderOptions,out:&mut[u8])->Result<(),Error>{self.check_state()?;match &self.kind{
        Kind::Cpu(s)=>vapor_core::render::render_rgba8(s,c,o,out),
        #[cfg(all(feature="gpu",not(target_arch="wasm32")))] Kind::Gpu(g)=>vapor_core::render::render_rgba8(&g.snapshot(self.clock.clone())?,c,o,out),
        #[cfg(all(feature="gpu",not(target_arch="wasm32")))] Kind::Hybrid{cpu,..}=>vapor_core::render::render_rgba8(cpu,c,o,out),
    }}
}
#[cfg(test)] mod tests{
    use super::*;
    fn cfg()->Config{Config{cells:[4;3],..Config::default()}}
    #[test]fn cpu_contract(){let mut e=Engine::new(cfg()).unwrap();e.step_fixed(1).unwrap();assert_eq!(e.info().active,Mode::Cpu);assert_eq!(e.metrics().unwrap().ticks,1);}
    #[test]fn rejects_bad_scale(){let o=BackendOptions{mode:Mode::Hybrid,detail_scale:0,..BackendOptions::default()};assert!(o.validate(&cfg()).is_err());}
    #[test]fn cpu_cannot_claim_detail(){assert!(Engine::with_options(cfg(),BackendOptions{detail_scale:2,..BackendOptions::default()}).is_err());}
    #[cfg(not(feature="gpu"))] #[test]fn no_silent_gpu_substitution(){assert!(matches!(Engine::with_options(cfg(),BackendOptions{mode:Mode::Gpu,..BackendOptions::default()}),Err(Error::BackendUnavailable)));}
    #[cfg(not(feature="gpu"))] #[test]fn auto_fallback_is_reported(){let e=Engine::with_options(cfg(),BackendOptions{mode:Mode::Auto,flags:ALLOW_CPU_FALLBACK,..BackendOptions::default()}).unwrap();assert_eq!(e.info().requested,Mode::Auto);assert_eq!(e.info().active,Mode::Cpu);assert!(e.info().flags&8!=0);}
    #[test]fn hitch_drop_is_not_lost(){let mut e=Engine::new(cfg()).unwrap();let r=e.advance(1.).unwrap();assert_eq!(r.dropped_seconds,e.metrics().unwrap().dropped_seconds);}
}
