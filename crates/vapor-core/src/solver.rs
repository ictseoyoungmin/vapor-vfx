//! Deterministic, allocation-free-per-step MAC reference/runtime backend.
//! Face velocities are packed at integer lower faces in a one-cell padded array.
use crate::runtime::*;
use crate::transport::{ConservativeDensity,DensityBudget};
use crate::plume::{self,ResolvedPlumeOptions};
use crate::pressure::{OpenPressure,PressureReport};

#[derive(Clone,Copy,Debug,Default)]
#[repr(C)]
pub struct Cell {pub v:[f32;4],pub s:[f32;4]}
// s = density, temperature, pressure (velocity-potential units), solid mask.
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
#[repr(u32)]
pub enum Field {Density=0,Temperature=1,Pressure=2,Solid=3,Velocity=4}
impl Field {pub fn channels(self)->usize {if self==Self::Velocity {3}else{1}}}

#[derive(Clone,Debug,Default)]
pub struct Metrics {
    pub ticks:u64,pub time:f64,pub density_integral:f64,pub max_density:f32,
    pub max_speed:f32,pub divergence_rms:f64,pub pressure_residual_rms:f64,
    pub centroid:[f64;3],pub non_finite:u32,pub clamped_velocities:u64,
    pub dropped_seconds:f64,pub cpu_bytes:u64,
}

pub struct Simulation {
    cfg:Config,a:Vec<Cell>,b:Vec<Cell>,hat:Vec<Cell>,aux:Vec<[f32;4]>,
    scene: Scene,
    clock:Clock,failed:bool,clamps:u64,
    conservative:Option<ConservativeDensity>,
    resolved:Option<ResolvedPlumeOptions>,
    pressure:Option<OpenPressure>,
}
impl Simulation {
    pub fn new(cfg:Config)->Result<Self,Error> {
        cfg.validate()?;let n=cfg.padded_len()?;
        fn alloc<T:Clone+Default>(n:usize)->Result<Vec<T>,Error>{let mut v=Vec::new();v.try_reserve_exact(n).map_err(|_|Error::Capacity)?;v.resize(n,T::default());Ok(v)}
        Ok(Self {cfg,a:alloc(n)?,b:alloc(n)?,hat:alloc(n)?,aux:alloc(n)?,
            scene: Scene::default(),
            clock:Clock::default(),failed:false,clamps:0,conservative:None,resolved:None,pressure:None})
    }
    /// Opt-in CPU research candidate. Existing constructors/backends are unchanged.
    /// Density uses finite-volume MUSCL + source-space integration; temperature
    /// and momentum still use the legacy MAC solver. Obstacles are unsupported.
    pub fn new_conservative_density(cfg:Config)->Result<Self,Error>{
        let mut sim=Self::new(cfg)?;
        sim.conservative=Some(ConservativeDensity::new(&sim.cfg)?);Ok(sim)
    }
    /// Open-domain conservative density with residual-gated pressure; legacy source.
    pub fn new_converged_density(cfg:Config)->Result<Self,Error>{
        if cfg.boundary!=Boundary::Open{return Err(Error::Unsupported);}
        let mut sim=Self::new_conservative_density(cfg)?;
        sim.pressure=Some(OpenPressure::new(&sim.cfg)?);Ok(sim)
    }
    /// Opt-in resolved physical source + conservative density, uniform local grid.
    pub fn new_resolved_plume(cfg:Config, options:ResolvedPlumeOptions)->Result<Self,Error>{
        options.validate()?;let mut sim=Self::new_converged_density(cfg)?;
        sim.resolved=Some(options);Ok(sim)
    }
    pub fn pressure_report(&self)->Option<PressureReport>{self.pressure.as_ref().and_then(|p|p.report)}
    pub fn density_budget(&self)->Option<DensityBudget>{self.conservative.as_ref().and_then(|c|c.budget)}
    pub fn allocated_cpu_bytes(&self)->usize {self.cfg.estimated_cpu_bytes().unwrap_or(0)+self.conservative.as_ref().map_or(0,ConservativeDensity::bytes)+self.pressure.as_ref().map_or(0,OpenPressure::bytes)}
    pub fn config(&self)->&Config {&self.cfg}
    pub fn time(&self)->f64 {self.clock.ticks as f64*self.cfg.fixed_dt as f64}
    pub fn scene(&self) -> &Scene { &self.scene }
    pub fn set_emitter(&mut self, id:u32, e:Emitter)->Result<(),Error>{if self.resolved.is_some(){plume::validate_source(&e.clone().validated(&self.cfg)?,&self.cfg)?;}self.scene.set_emitter(&self.cfg,id,e)}
    pub fn remove_emitter(&mut self,id:u32)->Result<(),Error>{self.scene.remove_emitter(id)}
    pub fn set_profile(&mut self,id:u32,p:Option<EmissionProfile>)->Result<(),Error>{self.scene.set_profile(id,p)}
    pub fn set_obstacle(&mut self,id:u32,o:Obstacle)->Result<(),Error>{if self.conservative.is_some()&&o.enabled{return Err(Error::Unsupported);}self.scene.set_obstacle(&self.cfg,id,o)}
    pub fn remove_obstacle(&mut self,id:u32)->Result<(),Error>{self.scene.remove_obstacle(id)}
    /// Borrowed packed MAC cells; intended for one-way GPU upload, never a C pointer.
    pub fn mac_cells(&self) -> &[Cell] { &self.a }
    pub fn divergence_rhs(&self) -> &[[f32;4]] { &self.aux }
    pub fn clock(&self) -> &Clock { &self.clock }
    /// Explicit diagnostic/import path. Validates everything before committing a state.
    pub fn import_mac(&mut self, cells:&[Cell], rhs:&[[f32;4]], clock:Clock, clamps:u64) -> Result<(),Error> {
        if cells.len()!=self.a.len() || rhs.len()!=self.aux.len() ||
           !clock.accumulator.is_finite() || clock.accumulator<0. || clock.accumulator>self.cfg.fixed_dt as f64 ||
           !clock.dropped_total.is_finite() || clock.dropped_total<0. {
            return Err(Error::InvalidArgument("invalid MAC snapshot layout or clock"));
        }
        if cells.iter().any(|c| c.v.iter().chain(c.s.iter()).any(|x|!x.is_finite())) ||
           rhs.iter().flatten().any(|x| !x.is_finite()) {return Err(Error::NonFiniteState);}
        if self.conservative.is_some()&&cells.iter().any(|c|c.s[0]<0.||c.s[3]>0.5){return Err(Error::Unsupported);}
        if let Some(c)=&mut self.conservative{c.budget=None;}
        if let Some(p)=&mut self.pressure{p.report=None;}
        self.a.copy_from_slice(cells); self.aux.copy_from_slice(rhs); self.clock=clock;
        self.clamps=clamps; self.failed=false; Ok(())
    }
    /// Clear fields/time but retain emitter, obstacle and profile definitions.
    pub fn reset(&mut self){self.a.fill(Cell::default());self.b.fill(Cell::default());self.hat.fill(Cell::default());self.aux.fill([0.;4]);self.clock=Clock::default();self.failed=false;self.clamps=0;if let Some(c)=&mut self.conservative{c.budget=None;}if let Some(p)=&mut self.pressure{p.report=None;}}
    pub fn step_fixed(&mut self,count:u32)->Result<(),Error>{
        if count>MAX_STEPS_PER_CALL{return Err(Error::InvalidArgument("too many steps in one call"));}
        if self.failed{return Err(Error::NonFiniteState);}
        for _ in 0..count {self.step_one()?;}Ok(())
    }
    pub fn advance(&mut self,elapsed:f64)->Result<AdvanceReport,Error>{
        let (steps,residual,dropped)=self.clock.plan(elapsed,&self.cfg)?;
        self.step_fixed(steps)?;self.clock.accumulator=residual;self.clock.dropped_total+=dropped;
        Ok(AdvanceReport{steps,alpha:residual/self.cfg.fixed_dt as f64,dropped_seconds:dropped,simulated_seconds:self.time()})
    }
    fn step_one(&mut self)->Result<(),Error>{
        // Reject overflow before modifying any field. A failed step must not advance physics.
        let next_tick=self.clock.ticks.checked_add(1).ok_or(Error::Capacity)?;
        let sources = self.scene.sources(&self.cfg,self.time())?;
        if let Some(c)=&mut self.conservative{c.prepare(&self.cfg,&sources)?;}
        if let Some(p)=&mut self.pressure{p.report=None;}
        let clamps_before=self.clamps;
        let k=Kernel{cfg:&self.cfg,sources:&sources,obstacles:&self.scene.obstacles,resolved:self.resolved,time:self.time()};
        k.classify(&mut self.a);
        k.force(&self.a,&mut self.b);std::mem::swap(&mut self.a,&mut self.b);
        k.curl(&self.a,&mut self.aux);
        k.vorticity(&self.a,&self.aux,&mut self.b);std::mem::swap(&mut self.a,&mut self.b);
        if let Err(e)=limit_state(&mut self.a,self.cfg.max_velocity,&mut self.clamps){self.failed=true;return Err(e);}
        k.advect_velocity(&self.a,&mut self.hat);
        k.correct_velocity(&self.a,&self.hat,&mut self.b);std::mem::swap(&mut self.a,&mut self.b);
        k.boundaries(&self.a,&mut self.b,true);std::mem::swap(&mut self.a,&mut self.b);
        k.divergence(&mut self.a,&mut self.aux);
        if let Some(p)=&mut self.pressure{if let Err(e)=p.solve(&mut self.a,&self.aux,&self.cfg){self.failed=true;return Err(e);}}else{for _ in 0..self.cfg.pressure_iterations {k.sor(&mut self.a,&self.aux,0);k.sor(&mut self.a,&self.aux,1);}}
        k.project(&self.a,&mut self.b);std::mem::swap(&mut self.a,&mut self.b);
        k.boundaries(&self.a,&mut self.b,false);std::mem::swap(&mut self.a,&mut self.b);
        if let Err(e)=limit_state(&mut self.a,self.cfg.max_velocity,&mut self.clamps){self.failed=true;return Err(e);}
        if let Some(p)=&mut self.pressure {
            let n=k.n();let mut div2=0f64;
            for z in 0..n[2]{for y in 0..n[1]{for x in 0..n[0]{div2+=(k.div_at(&self.a,[x,y,z]) as f64).powi(2);}}}
            let actual=(div2/self.cfg.voxel_count() as f64).sqrt();
            let q=p.report.as_mut().ok_or(Error::Internal)?;q.projected_divergence_rms=Some(actual);
            if !actual.is_finite() || actual>(q.initial_divergence_rms*2e-4).max(2e-5) || self.clamps!=clamps_before {
                self.failed=true;return Err(Error::InvalidArgument("resolved velocity failed projection or clamp gate"));
            }
        }
        k.advect_scalar(&self.a,&mut self.hat);
        k.correct_scalar_source(&self.a,&self.hat,&mut self.b);
        if let Some(c)=&mut self.conservative{
            if let Err(e)=c.update(&self.a,&mut self.b,&self.cfg){self.failed=true;return Err(e);}
        }
        std::mem::swap(&mut self.a,&mut self.b);
        if let Err(e)=limit_state(&mut self.a,self.cfg.max_velocity,&mut self.clamps){self.failed=true;return Err(e);}
        self.clock.ticks=next_tick;Ok(())
    }
    pub fn field_len(&self,field:Field)->usize {self.cfg.voxel_count()*field.channels()}
    /// Copies an owned, dense [z,y,x,channels] snapshot; no internal pointer escapes.
    pub fn copy_field(&self,field:Field,out:&mut[f32])->Result<(),Error>{
        if out.len()<self.field_len(field){return Err(Error::BufferTooSmall);}
        let n=self.cfg.cells.map(|x|x as usize);let mut j=0;
        for z in 0..n[2]{for y in 0..n[1]{for x in 0..n[0]{let i=idx([x,y,z],n);let c=&self.a[i];
            if field==Field::Velocity{for axis in 0..3{let mut p=[x,y,z];p[axis]+=1;out[j]=0.5*(c.v[axis]+self.a[idx(p,n)].v[axis]);j+=1;}}
            else{out[j]=c.s[field as usize];j+=1;}
        }}}Ok(())
    }
    /// Linear 2-D atlas: width=nx, height=ny*nz, RGBA8=(density/cap,temp/16,solid,255).
    pub fn copy_atlas_rgba8(&self,out:&mut[u8])->Result<(),Error>{
        if out.len()<self.cfg.voxel_count()*4{return Err(Error::BufferTooSmall);}
        let n=self.cfg.cells.map(|x|x as usize);let mut j=0;
        for z in 0..n[2]{for y in 0..n[1]{for x in 0..n[0]{let c=&self.a[idx([x,y,z],n)];
            out[j]=(c.s[0]/self.cfg.density_cap*255.).clamp(0.,255.).round() as u8;
            out[j+1]=(c.s[1]/16.*255.).clamp(0.,255.).round() as u8;
            out[j+2]=if c.s[3]>0.5{255}else{0};out[j+3]=255;j+=4;
        }}}Ok(())
    }
    pub fn metrics(&self)->Metrics{
        let n=self.cfg.cells.map(|x|x as usize);let mut m=Metrics{ticks:self.clock.ticks,time:self.time(),clamped_velocities:self.clamps,dropped_seconds:self.clock.dropped_total,cpu_bytes:self.allocated_cpu_bytes() as u64,..Metrics::default()};
        let mut total=0f64;let mut sum=[0f64;3];let mut div2=0.;let mut res2=0.;let mut count=0;
        let k=Kernel{cfg:&self.cfg,sources:&[],obstacles:&self.scene.obstacles,resolved:None,time:0.};
        for z in 0..n[2]{for y in 0..n[1]{for x in 0..n[0]{let p=[x,y,z];let i=idx(p,n);let c=self.a[i];
            m.non_finite+=c.v.iter().chain(c.s.iter()).filter(|v|!v.is_finite()).count() as u32;
            if c.s[3]>0.5{continue;}
            let density=c.s[0] as f64;total+=density;m.max_density=m.max_density.max(c.s[0]);
            for axis in 0..3{sum[axis]+=density*(self.cfg.origin[axis] as f64+(p[axis] as f64+0.5)*self.cfg.cell_size as f64);}
            m.max_speed=m.max_speed.max(len(cell_velocity(&self.a,p,n)));
            let d=k.div_at(&self.a,p);div2+=(d as f64).powi(2);count+=1;
            let (sum_p,denom)=k.pressure_sum(&self.a,p);let residual=(sum_p-denom*c.s[2])/(self.cfg.cell_size*self.cfg.cell_size)-self.aux[i][3];res2+=(residual as f64).powi(2);
        }}}
        if total>0.{for (axis,value) in sum.iter().enumerate(){m.centroid[axis]=*value/total;}}
        m.density_integral=total*(self.cfg.cell_size as f64).powi(3);
        if count>0{m.divergence_rms=(div2/count as f64).sqrt();m.pressure_residual_rms=(res2/count as f64).sqrt();}m
    }
    pub(crate) fn sample_density(&self,p:V3)->f32 {sample_scalar(&self.a,mul(sub(p,self.cfg.origin),1./self.cfg.cell_size),self.cfg.cells.map(|n|n as usize),0)}
}

// Bound advection before transport, not just after it. Clamps are explicit diagnostics;
// they break projection/conservation and should remain zero in a well-tuned scene.
fn limit_state(state:&mut[Cell],cap:f32,clamps:&mut u64)->Result<(),Error>{
    for c in state {
        if c.v.iter().chain(c.s.iter()).any(|x|!x.is_finite()){return Err(Error::NonFiniteState);}
        for v in &mut c.v[..3] {if v.abs()>cap{*v=(*v).clamp(-cap,cap);*clamps=clamps.saturating_add(1);}}
    }Ok(())
}

#[inline] pub(crate) fn idx(c:[usize;3],n:[usize;3])->usize {c[0]+(n[0]+1)*(c[1]+(n[1]+1)*c[2])}
fn coords(i:usize,n:[usize;3])->[usize;3]{let x=i%(n[0]+1);let q=i/(n[0]+1);[x,q%(n[1]+1),q/(n[1]+1)]}
fn inside(c:[i32;3],n:[usize;3])->bool {(0..3).all(|a|c[a]>=0&&(c[a] as usize)<n[a])}
fn centre(c:[usize;3])->V3 {c.map(|v|v as f32+0.5)}
fn face(c:[usize;3],a:usize)->V3{let mut p=centre(c);p[a]-=0.5;p}
fn face_valid(c:[usize;3],n:[usize;3],a:usize)->bool{(0..3).all(|j|c[j]<n[j]+usize::from(a==j))}
fn solid(s:&[Cell],c:[i32;3],n:[usize;3])->bool{inside(c,n)&&s[idx(c.map(|x|x as usize),n)].s[3]>0.5}
fn cell_velocity(s:&[Cell],c:[usize;3],n:[usize;3])->V3{
    std::array::from_fn(|a|{let mut q=c;q[a]+=1;0.5*(s[idx(c,n)].v[a]+s[idx(q,n)].v[a])})
}
fn sample(s:&[Cell],p:V3,n:[usize;3],channel:usize,velocity:bool)->f32{
    if !velocity&&(0..3).any(|a|p[a]<0.||p[a]>n[a] as f32){return 0.;}
    let max: [usize;3]=std::array::from_fn(|a|n[a]-1+usize::from(velocity&&a==channel));
    let q:V3=std::array::from_fn(|a|(p[a]-if velocity&&a==channel{0.}else{0.5}).clamp(0.,max[a] as f32));
    let b=q.map(|v|v.floor() as usize);let f:V3=std::array::from_fn(|a|q[a]-b[a] as f32);let mut result=0.;
    for z in 0..2{for y in 0..2{for x in 0..2{let d=[x,y,z];let c=std::array::from_fn(|a|(b[a]+d[a]).min(max[a]));let w=(0..3).map(|a|if d[a]==0{1.-f[a]}else{f[a]}).product::<f32>();let v=s[idx(c,n)];result+=w*if velocity{v.v[channel]}else{v.s[channel]};}}}result
}
fn sample_scalar(s:&[Cell],p:V3,n:[usize;3],channel:usize)->f32{sample(s,p,n,channel,false)}
fn sample_velocity(s:&[Cell],p:V3,n:[usize;3])->V3{std::array::from_fn(|a|sample(s,p,n,a,true))}
fn extrema(s:&[Cell],p:V3,n:[usize;3],a:usize,velocity:bool)->(f32,f32){
    let max:[i32;3]=std::array::from_fn(|j|n[j] as i32-1+i32::from(velocity&&a==j));
    let b:[i32;3]=std::array::from_fn(|j|(p[j]-if velocity&&j==a{0.}else{0.5}).floor() as i32);
    let(mut lo,mut hi)=(f32::INFINITY,f32::NEG_INFINITY);
    for z in 0..2{for y in 0..2{for x in 0..2{let d=[x,y,z];let c=std::array::from_fn(|j|(b[j]+d[j]).clamp(0,max[j]) as usize);let v=s[idx(c,n)];let v=if velocity{v.v[a]}else{v.s[a]};lo=lo.min(v);hi=hi.max(v);}}}(lo,hi)
}
struct Kernel<'a>{cfg:&'a Config,sources:&'a[Option<Emitter>],obstacles:&'a[Option<Obstacle>],resolved:Option<ResolvedPlumeOptions>,time:f64}
impl Kernel<'_>{
    fn n(&self)->[usize;3]{self.cfg.cells.map(|v|v as usize)}
    fn world(&self,p:V3)->V3{add(self.cfg.origin,mul(p,self.cfg.cell_size))}
    fn solid_velocity(&self,p:V3)->V3{let mut d=f32::MAX;let mut v=[0.;3];for o in self.obstacles.iter().flatten(){let q=o.sdf(p);if q<d{d=q;v=o.velocity;}}v}
    fn classify(&self,s:&mut[Cell]){let n=self.n();for (i,c) in s.iter_mut().enumerate(){let p=coords(i,n);if (0..3).any(|a|p[a]>=n[a]){c.s=[0.;4];continue;}let world=self.world(centre(p));let is_solid=self.obstacles.iter().flatten().any(|o|o.sdf(world)<0.);c.s[3]=if is_solid {1.} else {0.};if is_solid{c.s[0]=0.;c.s[1]=0.;c.s[2]=0.;}}}
    fn trace(&self,s:&[Cell],p:V3,dt:f32)->V3{let n=self.n();let k=dt/self.cfg.cell_size;let v=sample_velocity(s,p,n);let mid=sub(p,mul(v,0.5*k));let v2=sample_velocity(s,mid,n);let end=sub(p,mul(v2,k));
        if self.obstacles.iter().all(Option::is_none){return end;}
        let diff=sub(end,p);let count=(len(diff)*2.).ceil().clamp(1.,64.) as u32;let mut last=p;
        for j in 1..=count{let q=add(p,mul(diff,j as f32/count as f32));let c=q.map(|v|v.floor() as i32);if solid(s,c,n){return last;}last=q;}end
    }
    fn force(&self,src:&[Cell],dst:&mut[Cell]){let n=self.n();let dt=self.cfg.fixed_dt;
        for i in 0..src.len(){let c=coords(i,n);let mut out=src[i];for a in 0..3{if !face_valid(c,n,a){out.v[a]=0.;continue;}let p=face(c,a);let mut v=src[i].v[a];v+=(self.cfg.wind[a]-v)*(1.-(-self.cfg.drag*dt).exp());
            if a==1{v+=dt*(self.cfg.buoyancy*sample_scalar(src,p,n,1)-self.cfg.density_weight*sample_scalar(src,p,n,0));}
            let world=self.world(p);for e in self.sources.iter().flatten(){let (w,m,rate)=if let Some(o)=self.resolved{let(w,m)=plume::sample(e,world,self.cfg.cell_size,a,o,self.time);(w,m,plume::rate(e))}else{(e.weight(world,self.cfg.cell_size),1.,20.)};let gain=1.-(-rate*w*dt).exp();v+=(e.direction[a]*e.speed*m-v)*gain;}
            out.v[a]=v;}dst[i]=out;}
    }
    fn curl(&self,src:&[Cell],aux:&mut[[f32;4]]){let n=self.n();let inv=0.5/self.cfg.cell_size;
        for (i,output) in aux.iter_mut().enumerate(){let c=coords(i,n);if (0..3).any(|a|c[a]>=n[a]){*output=[0.;4];continue;}let p=centre(c);
            let derivatives:[V3;3]=std::array::from_fn(|a|mul(sub(sample_velocity(src,add(p,axis(a)),n),sample_velocity(src,sub(p,axis(a)),n)),inv));
            let w=[derivatives[1][2]-derivatives[2][1],derivatives[2][0]-derivatives[0][2],derivatives[0][1]-derivatives[1][0]];*output=[w[0],w[1],w[2],len(w)];}
    }
    fn confinement(&self,c:[usize;3],aux:&[[f32;4]])->V3{let n=self.n();if (0..3).any(|a|c[a]==0||c[a]+1>=n[a]){return [0.;3];}
        let g:V3=std::array::from_fn(|a|{let mut lo=c;let mut hi=c;lo[a]-=1;hi[a]+=1;aux[idx(hi,n)][3]-aux[idx(lo,n)][3]});let unit=mul(g,1./(len(g)+1e-6));let w=aux[idx(c,n)];mul(cross(unit,[w[0],w[1],w[2]]),self.cfg.vorticity*self.cfg.cell_size)
    }
    fn vorticity(&self,src:&[Cell],aux:&[[f32;4]],dst:&mut[Cell]){let n=self.n();for i in 0..src.len(){let c=coords(i,n);let mut out=src[i];let f=self.confinement(c,aux);for a in 0..3{if c[a]>0&&face_valid(c,n,a){let mut lo=c;lo[a]-=1;out.v[a]+=self.cfg.fixed_dt*0.5*(f[a]+self.confinement(lo,aux)[a]);}}dst[i]=out;}}
    fn advect_velocity(&self,src:&[Cell],dst:&mut[Cell]){let n=self.n();for i in 0..src.len(){let c=coords(i,n);let mut out=src[i];for a in 0..3{if face_valid(c,n,a){let p=self.trace(src,face(c,a),self.cfg.fixed_dt);out.v[a]=sample(src,p,n,a,true);}}dst[i]=out;}}
    fn correct_velocity(&self,src:&[Cell],hat:&[Cell],dst:&mut[Cell]){let n=self.n();for i in 0..src.len(){let c=coords(i,n);let mut out=src[i];for a in 0..3{if face_valid(c,n,a){let p=face(c,a);let back=self.trace(src,p,self.cfg.fixed_dt);let forward=self.trace(src,p,-self.cfg.fixed_dt);let q=hat[i].v[a]+0.5*(src[i].v[a]-sample(hat,forward,n,a,true));let(lo,hi)=extrema(src,back,n,a,true);let cfl=len(sub(back,p));let correction=(2./cfl.max(1.)).min(1.);out.v[a]=hat[i].v[a]+correction*(q.clamp(lo,hi)-hat[i].v[a]);}}dst[i]=out;}}
    fn boundaries(&self,src:&[Cell],dst:&mut[Cell],extrapolate:bool){
        let n=self.n();for i in 0..src.len(){let c=coords(i,n);let mut out=src[i];
            for a in 0..3{if !face_valid(c,n,a){out.v[a]=0.;continue;}
                let hi=c.map(|v|v as i32);let mut lo=hi;lo[a]-=1;
                if solid(src,hi,n)||solid(src,lo,n){out.v[a]=self.solid_velocity(self.world(face(c,a)))[a];continue;}
                if c[a]==0||c[a]==n[a]{if self.cfg.boundary==Boundary::Closed{out.v[a]=0.;}else{
                    let mut q=c;q[a]=if c[a]==0{1}else{n[a]-1};
                    let v=if extrapolate{src[idx(q,n)].v[a]}else{src[i].v[a]};
                    // Open pressure boundary admits ambient air after projection.
                    // Clipping inflow here would invalidate the just-solved Poisson equation.
                    out.v[a]=if !extrapolate {v} else if c[a]==0{v.min(0.)}else{v.max(0.)};
                }}
            }dst[i]=out;
        }
    }
    fn div_at(&self,s:&[Cell],c:[usize;3])->f32{let n=self.n();let mut d=0.;for a in 0..3{let mut hi=c;hi[a]+=1;d+=s[idx(hi,n)].v[a]-s[idx(c,n)].v[a];}d/self.cfg.cell_size}
    fn divergence(&self,s:&mut[Cell],aux:&mut[[f32;4]]){let n=self.n();for i in 0..s.len(){let c=coords(i,n);if (0..3).any(|a|c[a]>=n[a])||s[i].s[3]>0.5{aux[i][3]=0.;s[i].s[2]=0.;continue;}aux[i][3]=self.div_at(s,c);s[i].s[2]=0.;}}
    fn pressure_sum(&self,s:&[Cell],c:[usize;3])->(f32,f32){let n=self.n();let mut sum=0.;let mut count=0.;for a in 0..3{for sign in [-1,1]{let mut q=c.map(|v|v as i32);q[a]+=sign;if inside(q,n){let near=s[idx(q.map(|v|v as usize),n)];if near.s[3]<=0.5{sum+=near.s[2];count+=1.;}}else if self.cfg.boundary==Boundary::Open{count+=1.;}}}(sum,count)}
    fn sor(&self,s:&mut[Cell],aux:&[[f32;4]],colour:usize){let n=self.n();for z in 0..n[2]{for y in 0..n[1]{for x in 0..n[0]{if (x+y+z)%2!=colour{continue;}let c=[x,y,z];let i=idx(c,n);if s[i].s[3]>0.5{continue;}let(sum,count)=self.pressure_sum(s,c);if count>0.{let q=(sum-aux[i][3]*self.cfg.cell_size*self.cfg.cell_size)/count;s[i].s[2]+=self.cfg.sor_omega*(q-s[i].s[2]);}}}}}
    fn project(&self,src:&[Cell],dst:&mut[Cell]){let n=self.n();for i in 0..src.len(){let c=coords(i,n);let mut out=src[i];for a in 0..3{if !face_valid(c,n,a){continue;}let hi=c.map(|v|v as i32);let mut lo=hi;lo[a]-=1;if solid(src,hi,n)||solid(src,lo,n){out.v[a]=self.solid_velocity(self.world(face(c,a)))[a];continue;}
            if self.cfg.boundary==Boundary::Closed&&(!inside(hi,n)||!inside(lo,n)){out.v[a]=0.;continue;}
            let pressure=|p:[i32;3]|if inside(p,n){src[idx(p.map(|v|v as usize),n)].s[2]}else{0.};out.v[a]-=(pressure(hi)-pressure(lo))/self.cfg.cell_size;
        }dst[i]=out;}}
    fn advect_scalar(&self,src:&[Cell],dst:&mut[Cell]){let n=self.n();for i in 0..src.len(){let c=coords(i,n);let mut out=src[i];if (0..3).all(|a|c[a]<n[a]){let p=self.trace(src,centre(c),self.cfg.fixed_dt);for a in 0..2{out.s[a]=sample_scalar(src,p,n,a);}}dst[i]=out;}}
    fn correct_scalar_source(&self,src:&[Cell],hat:&[Cell],dst:&mut[Cell]){let n=self.n();let dt=self.cfg.fixed_dt;for i in 0..src.len(){let c=coords(i,n);let mut out=src[i];if (0..3).any(|a|c[a]>=n[a])||src[i].s[3]>0.5{out.s[0]=0.;out.s[1]=0.;dst[i]=out;continue;}
        let p=centre(c);let back=self.trace(src,p,dt);let forward=self.trace(src,p,-dt);
        for a in 0..2{if (0..3).any(|j|back[j]<0.||back[j]>n[j] as f32){out.s[a]=0.;continue;}let q=hat[i].s[a]+0.5*(src[i].s[a]-sample_scalar(hat,forward,n,a));let(lo,hi)=extrema(src,back,n,a,false);let cfl=len(sub(back,p));let gain=(2./cfl.max(1.)).min(1.);out.s[a]=(hat[i].s[a]+gain*(q.clamp(lo,hi)-hat[i].s[a])).max(0.);}
        out.s[0]*=(-self.cfg.density_decay*dt).exp();out.s[1]*=(-self.cfg.cooling*dt).exp();
        let world=self.world(p);for e in self.sources.iter().flatten(){let (w,rate)=if let Some(o)=self.resolved{(plume::sample(e,world,self.cfg.cell_size,3,o,self.time).0,plume::rate(e))}else{(e.weight(world,self.cfg.cell_size),20.)};if self.resolved.is_none(){out.s[0]+=e.density_rate*w*e.density_scale(self.cfg.cell_size)*dt;}out.s[1]+=(e.temperature-out.s[1]).max(0.)*(1.-(-rate*w*dt).exp());}
        out.s[0]=out.s[0].min(self.cfg.density_cap);dst[i]=out;
    }}
}

#[cfg(test)]
mod tests {
 use super::*;
 fn small()->Config{Config{cells:[8,10,8],cell_size:0.06,pressure_iterations:80,..Config::default()}}
 #[test]
 fn metrics_reports_vector_speed_not_one_axis() {
     let mut s=Simulation::new(small()).unwrap();
     for cell in &mut s.a {cell.v=[3.,4.,0.,0.];}
     assert_eq!(s.metrics().max_speed,5.);
 }
 #[test]
 fn malformed_mac_import_is_transactional() {
     let mut s=Simulation::new(small()).unwrap();
     let before=s.mac_cells().to_vec();let rhs=s.divergence_rhs().to_vec();
     let mut invalid=before.clone();invalid[0].s[0]=f32::NAN;
     assert!(s.import_mac(&invalid,&rhs,Clock::default(),0).is_err());
     assert_eq!(s.metrics().non_finite,0);
     assert_eq!(s.metrics().density_integral,0.);
     assert_eq!(s.time(),0.);
 }
 #[test]fn empty_stays_empty(){let mut s=Simulation::new(small()).unwrap();s.step_fixed(6).unwrap();let m=s.metrics();assert_eq!(m.density_integral,0.);assert_eq!(m.non_finite,0);assert_eq!(m.divergence_rms,0.);}
 #[test]fn source_emits_and_stays_finite(){let mut s=Simulation::new(small()).unwrap();s.set_emitter(0,Emitter{position:[0.24,0.1,0.24],..Emitter::default()}).unwrap();s.step_fixed(20).unwrap();let m=s.metrics();assert!(m.density_integral>0.);assert_eq!(m.non_finite,0);assert!(m.max_density<=s.cfg.density_cap);}
 #[test]fn reset_retains_sources(){let mut s=Simulation::new(small()).unwrap();s.set_emitter(0,Emitter::default()).unwrap();s.step_fixed(2).unwrap();s.reset();assert_eq!(s.time(),0.);assert_eq!(s.metrics().density_integral,0.);s.step_fixed(2).unwrap();assert!(s.metrics().density_integral>0.);}
 #[test]fn deterministic_replay(){let mut a=Simulation::new(small()).unwrap();let mut b=Simulation::new(small()).unwrap();for s in [&mut a,&mut b]{s.set_emitter(0,Emitter::default()).unwrap();s.step_fixed(8).unwrap();}let mut x=vec![0.;a.field_len(Field::Density)];let mut y=x.clone();a.copy_field(Field::Density,&mut x).unwrap();b.copy_field(Field::Density,&mut y).unwrap();assert_eq!(x,y);}
 #[test]fn clock_caps_hitches_without_spiral(){let mut s=Simulation::new(small()).unwrap();let r=s.advance(1.).unwrap();assert_eq!(r.steps,4);assert!(r.dropped_seconds>0.9);assert!(r.alpha>=0.&&r.alpha<=1.);}
 #[test]fn partitioned_time_matches_fixed(){let cfg=small();let dt=cfg.fixed_dt as f64;let mut a=Simulation::new(cfg.clone()).unwrap();let mut b=Simulation::new(cfg).unwrap();for _ in 0..10{a.advance(dt/2.).unwrap();}b.step_fixed(5).unwrap();assert_eq!(a.metrics().ticks,b.metrics().ticks);}
 #[test]fn solid_is_empty(){let mut s=Simulation::new(small()).unwrap();s.set_emitter(0,Emitter::default()).unwrap();s.set_obstacle(0,Obstacle::sphere([0.3,0.15,0.3],0.15)).unwrap();s.step_fixed(4).unwrap();for c in &s.a{if c.s[3]>0.5{assert_eq!(c.s[0],0.);}}}
 #[test]fn projection_reduces_closed_divergence(){let cfg=Config{boundary:Boundary::Closed,pressure_iterations:180,..small()};let mut s=Simulation::new(cfg).unwrap();let n=s.cfg.cells.map(|x|x as usize);for i in 0..s.a.len(){let c=coords(i,n);s.a[i].v[0]=((c[0]*17+c[1]*3+c[2]*5) as f32).sin();}
  let k=Kernel{cfg:&s.cfg,sources:&[],obstacles:&[],resolved:None,time:0.};k.boundaries(&s.a,&mut s.b,true);std::mem::swap(&mut s.a,&mut s.b);k.divergence(&mut s.a,&mut s.aux);let before=s.aux.iter().map(|v|(v[3] as f64).powi(2)).sum::<f64>();for _ in 0..180{k.sor(&mut s.a,&s.aux,0);k.sor(&mut s.a,&s.aux,1);}k.project(&s.a,&mut s.b);k.boundaries(&s.b,&mut s.a,false);std::mem::swap(&mut s.a,&mut s.b);let mut after=0.;for z in 0..n[2]{for y in 0..n[1]{for x in 0..n[0]{after+=(k.div_at(&s.b,[x,y,z]) as f64).powi(2);}}}assert!(after<before*0.01,"before {before} after {after}");
 }
 #[test]fn invalid_inputs_rejected(){assert!(Simulation::new(Config{cells:[u32::MAX;3],..small()}).is_err());let mut s=Simulation::new(small()).unwrap();assert!(s.advance(f64::NAN).is_err());assert!(s.step_fixed(601).is_err());assert!(s.set_emitter(32,Emitter::default()).is_err());assert!(s.set_emitter(0,Emitter{direction:[0.;3],..Emitter::default()}).is_err());assert!(s.copy_field(Field::Density,&mut[0.;2]).is_err());}
 #[test]fn atlas_layout_and_alpha(){let s=Simulation::new(small()).unwrap();let mut a=vec![0;s.cfg.voxel_count()*4];s.copy_atlas_rgba8(&mut a).unwrap();assert!(a.chunks_exact(4).all(|p|p==[0,0,0,255]));}
 #[test]
 fn open_boundary_does_not_undo_projection() {
     let cfg=Config{cells:[6,8,6],cell_size:0.1,pressure_iterations:256,vorticity:0.,..Config::default()};
     let mut sim=Simulation::new(cfg).unwrap();
     let n=sim.cfg.cells.map(|v|v as usize);
     for z in 2..4 {for y in 2..5 {for x in 2..4 {
         sim.a[idx([x,y,z],n)].v[1]=0.3;
     }}}
     let k=Kernel{cfg:&sim.cfg,sources:&[],obstacles:&[],resolved:None,time:0.};
     k.boundaries(&sim.a,&mut sim.b,true);std::mem::swap(&mut sim.a,&mut sim.b);
     k.divergence(&mut sim.a,&mut sim.aux);
     for _ in 0..256 {k.sor(&mut sim.a,&sim.aux,0);k.sor(&mut sim.a,&sim.aux,1);}
     k.project(&sim.a,&mut sim.b);std::mem::swap(&mut sim.a,&mut sim.b);
     let projected=sim.a.clone();
     k.boundaries(&sim.a,&mut sim.b,false);
     let mut ambient_inflow=false;
     for i in 0..projected.len() {let c=coords(i,n);
         for a in 0..3 {if face_valid(c,n,a) && (c[a]==0||c[a]==n[a]) {
             assert_eq!(projected[i].v[a],sim.b[i].v[a],"post-projection boundary changed flux");
             ambient_inflow|=if c[a]==0 {sim.b[i].v[a]>0.}else{sim.b[i].v[a]<0.};
         }}
     }
     assert!(ambient_inflow,"the chosen scene must actually exercise ambient inflow");
     std::mem::swap(&mut sim.a,&mut sim.b);
     let metrics=sim.metrics();
     assert!(metrics.divergence_rms<1e-4,"{:?}",metrics);
     assert!((metrics.divergence_rms-metrics.pressure_residual_rms).abs()<1e-5);
 }
 #[test]
 fn clock_overflow_preserves_fields() {
     let mut sim=Simulation::new(small()).unwrap();
     sim.set_emitter(0,Emitter{position:[0.24,0.1,0.24],..Emitter::default()}).unwrap();
     sim.clock.ticks=u64::MAX;
     let before:Vec<_>=sim.mac_cells().iter().map(|c|(c.v,c.s)).collect();
     assert_eq!(sim.step_fixed(1),Err(Error::Capacity));
     assert_eq!(sim.clock.ticks,u64::MAX);
     let after:Vec<_>=sim.mac_cells().iter().map(|c|(c.v,c.s)).collect();
     assert_eq!(before,after);
 }

}
