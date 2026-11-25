use crate::breath::BreathProfile;
use std::fmt;

pub const MAX_EMITTERS: usize = 32;
pub const MAX_OBSTACLES: usize = 32;
pub const MAX_CELLS: usize = 2_097_152;
pub const MAX_STEPS_PER_CALL: u32 = 600;

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Error {
    InvalidConfig(&'static str), InvalidArgument(&'static str), Capacity,
    NonFiniteState, InvalidHandle, BufferTooSmall, Internal,
    BackendUnavailable, GpuFailure, Unsupported,
}
impl fmt::Display for Error {
    fn fmt(&self,f:&mut fmt::Formatter<'_>)->fmt::Result {
        match self {
            Self::InvalidConfig(s)|Self::InvalidArgument(s)=>write!(f,"{s}"),
            Self::Capacity=>write!(f,"resource limit exceeded"),
            Self::NonFiniteState=>write!(f,"non-finite simulation state; reset required"),
            Self::InvalidHandle=>write!(f,"invalid or released handle"),
            Self::BufferTooSmall=>write!(f,"output buffer is too small"),
            Self::Internal=>write!(f,"internal failure"),
            Self::BackendUnavailable=>write!(f,"requested GPU backend is unavailable"),
            Self::GpuFailure=>write!(f,"GPU operation failed; recreate the simulation"),
            Self::Unsupported=>write!(f,"operation is unsupported by this backend"),
        }
    }
}
impl std::error::Error for Error {}

pub type V3 = [f32;3];
pub(crate) fn add(a:V3,b:V3)->V3 {[a[0]+b[0],a[1]+b[1],a[2]+b[2]]}
pub(crate) fn sub(a:V3,b:V3)->V3 {[a[0]-b[0],a[1]-b[1],a[2]-b[2]]}
pub(crate) fn mul(a:V3,s:f32)->V3 {[a[0]*s,a[1]*s,a[2]*s]}
pub(crate) fn dot(a:V3,b:V3)->f32 {a[0]*b[0]+a[1]*b[1]+a[2]*b[2]}
pub(crate) fn len(a:V3)->f32 {dot(a,a).sqrt()}
pub(crate) fn cross(a:V3,b:V3)->V3 {[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]}
pub(crate) fn finite(a:V3)->bool {a.iter().all(|v|v.is_finite())}
pub(crate) fn smooth(x:f32)->f32 {let t=x.clamp(0.,1.);t*t*(3.-2.*t)}
pub(crate) fn axis(a:usize)->V3 {let mut v=[0.;3];v[a]=1.;v}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(u32)]
pub enum Boundary { Open = 0, Closed = 1 }

#[derive(Clone, Debug)]
pub struct Config {
    pub cells: [u32;3], pub cell_size: f32, pub origin: V3,
    pub fixed_dt: f32, pub max_substeps: u32, pub pressure_iterations: u32,
    pub sor_omega: f32, pub density_decay: f32, pub cooling: f32,
    pub buoyancy: f32, pub density_weight: f32, pub drag: f32,
    pub vorticity: f32, pub wind: V3, pub max_velocity: f32,
    pub density_cap: f32, pub boundary: Boundary,
}
impl Default for Config {
    fn default()->Self { Self {
        cells:[24,32,24],cell_size:0.025,origin:[0.;3],fixed_dt:1./60.,max_substeps:4,
        pressure_iterations:32,sor_omega:1.7,density_decay:0.35,cooling:1.,
        buoyancy:0.8,density_weight:0.02,drag:0.08,vorticity:0.15,wind:[0.;3],
        max_velocity:12.,density_cap:8.,boundary:Boundary::Open,
    }}
}
impl Config {
    pub fn validate(&self)->Result<(),Error> {
        if self.cells.iter().any(|n| !(4..=192).contains(n)) {return Err(Error::InvalidConfig("grid axes must be 4..192"));}
        if self.padded_len()? > MAX_CELLS {return Err(Error::Capacity);}
        if !self.cell_size.is_finite() || !(0.001..=10.).contains(&self.cell_size) {return Err(Error::InvalidConfig("cell_size must be 0.001..10 metres"));}
        if !finite(self.origin) || self.origin.iter().any(|x|x.abs()>1e6) || !finite(self.wind) {return Err(Error::InvalidConfig("origin/wind must be finite and origin within +/-1e6 m"));}
        if !self.fixed_dt.is_finite() || !(1./1000. ..=0.1).contains(&self.fixed_dt) {return Err(Error::InvalidConfig("fixed_dt must be 0.001..0.1 seconds"));}
        if !(1..=64).contains(&self.max_substeps)||!(1..=256).contains(&self.pressure_iterations) {return Err(Error::InvalidConfig("invalid substep or pressure iteration limit"));}
        if !self.sor_omega.is_finite()||!(0.1..1.99).contains(&self.sor_omega) {return Err(Error::InvalidConfig("SOR omega must be in [0.1,1.99)"));}
        for p in [self.density_decay,self.cooling,self.density_weight,self.drag,self.vorticity] {
            if !p.is_finite()||!(0. ..=100.).contains(&p) {return Err(Error::InvalidConfig("nonnegative physics parameter out of range"));}
        }
        if !self.buoyancy.is_finite()||self.buoyancy.abs()>100. {return Err(Error::InvalidConfig("invalid buoyancy"));}
        if !self.max_velocity.is_finite()||!(0.01..=100.).contains(&self.max_velocity)||len(self.wind)>self.max_velocity {return Err(Error::InvalidConfig("invalid speed limit or excessive wind"));}
        if !self.density_cap.is_finite()||!(0.01..=100.).contains(&self.density_cap) {return Err(Error::InvalidConfig("invalid density cap"));}
        // Segment collision traversal is bounded; reject unresolved transport rather than tunnelling.
        if self.max_velocity*3f32.sqrt()*self.fixed_dt/self.cell_size>32. {return Err(Error::InvalidConfig("configured maximum vector CFL exceeds 32; reduce dt/speed or enlarge cells"));}
        Ok(())
    }
    pub fn padded_len(&self)->Result<usize,Error> {
        self.cells.iter().try_fold(1usize,|a,&n|a.checked_mul(n as usize+1).ok_or(Error::Capacity))
    }
    pub fn voxel_count(&self)->usize {self.cells.iter().map(|&n|n as usize).product()}
    pub fn extent(&self)->V3 {self.cells.map(|n|n as f32*self.cell_size)}
    pub fn estimated_cpu_bytes(&self)->Result<usize,Error> {Ok(self.padded_len()?*(3*32+16))}
}

#[derive(Clone, Debug)]
pub struct Emitter {
    pub position: V3, pub direction: V3, pub radius: f32, pub length: f32,
    pub speed: f32, pub density_rate: f32, pub temperature: f32,
    pub enabled: bool,
}
impl Default for Emitter {
    fn default()->Self {Self {position:[0.3,0.15,0.3],direction:[0.,1.,0.],radius:0.045,length:0.08,speed:1.,density_rate:8.,temperature:1.,enabled:true}}
}
impl Emitter {
    pub fn validated(mut self, cfg:&Config)->Result<Self,Error> {
        if !finite(self.position)||self.position.iter().any(|v|v.abs()>1e6)||!finite(self.direction)||!len(self.direction).is_finite()||len(self.direction)<1e-6 {return Err(Error::InvalidArgument("invalid emitter position/direction"));}
        for v in [self.radius,self.length,self.speed,self.density_rate,self.temperature] {
            if !v.is_finite()||v<0.||v>1000. {return Err(Error::InvalidArgument("invalid emitter parameter"));}
        }
        if self.radius<=0. || self.speed>cfg.max_velocity {return Err(Error::InvalidArgument("emitter radius/speed invalid"));}
        self.direction=mul(self.direction,1./len(self.direction));Ok(self)
    }
    // A zero-length emitter is a short, radius-sized source, not zero volume.
    fn physical_length(&self)->f32 {if self.length>0. {self.length}else{self.radius}}
    // The smooth radial/axial kernel integral scales as radius² × length.
    // Compensate density injection for widening unresolved sources. Velocity and
    // temperature relaxation intentionally retain the widened support.
    pub(crate) fn density_scale(&self,dx:f32)->f32 {
        let l=self.physical_length();let r=self.radius/self.radius.max(dx*1.1);
        r*r*(l/l.max(dx))
    }
    pub(crate) fn weight(&self,p:V3,dx:f32)->f32 {
        if !self.enabled {return 0.;}
        let q=sub(p,self.position);let along=dot(q,self.direction);
        let length=self.physical_length().max(dx);let r=self.radius.max(dx*1.1);
        if along < -dx*0.5 || along>length+dx*0.5 {return 0.;}
        let radial=len(sub(q,mul(self.direction,along)));
        (1.-smooth(radial/r))*smooth((along+dx*0.5)/dx)*smooth((length+dx*0.5-along)/dx)
    }
}

#[derive(Clone, Copy, Debug)]
pub enum Shape { Capsule {a:V3,b:V3,radius:f32}, Box {min:V3,max:V3} }
#[derive(Clone, Debug)]
pub struct Obstacle {pub shape:Shape,pub velocity:V3,pub enabled:bool}
impl Obstacle {
    pub fn sphere(center:V3,radius:f32)->Self {Self {shape:Shape::Capsule{a:center,b:center,radius},velocity:[0.;3],enabled:true}}
    pub fn validate(&self,cfg:&Config)->Result<(),Error> {
        if !finite(self.velocity)||len(self.velocity)>cfg.max_velocity {return Err(Error::InvalidArgument("invalid obstacle velocity"));}
        match self.shape {
            Shape::Capsule{a,b,radius}=>if !finite(a)||!finite(b)||a.iter().chain(b.iter()).any(|v|v.abs()>1e6)||!radius.is_finite()||radius<=0.||radius>1000. {return Err(Error::InvalidArgument("invalid capsule"));},
            Shape::Box{min,max}=>if !finite(min)||!finite(max)||min.iter().chain(max.iter()).any(|v|v.abs()>1e6)||(0..3).any(|a|min[a]>=max[a]) {return Err(Error::InvalidArgument("invalid box"));},
        } Ok(())
    }
    pub(crate) fn sdf(&self,p:V3)->f32 {
        if !self.enabled {return f32::MAX;}
        match self.shape {
            Shape::Capsule{a,b,radius}=>{let ba=sub(b,a);let pa=sub(p,a);let h=(dot(pa,ba)/dot(ba,ba).max(1e-12)).clamp(0.,1.);len(sub(pa,mul(ba,h)))-radius},
            Shape::Box{min,max}=>{let c=mul(add(min,max),0.5);let h=mul(sub(max,min),0.5);let q=sub(sub(p,c).map(f32::abs),h);len(q.map(|v|v.max(0.)))+q[0].max(q[1]).max(q[2]).min(0.)},
        }
    }
}

#[derive(Clone, Debug)]
pub struct EmissionProfile {pub curve:BreathProfile,pub repeat:bool,pub start_time:f64}
impl EmissionProfile {
    pub fn apply(&self,time:f64,emitter:&Emitter)->Result<Emitter,Error> {
        let mut e=emitter.clone();let age=time-self.start_time;
        if age<0.||(!self.repeat&&age>=self.curve.duration_s) {e.enabled=false;return Ok(e);}
        let t=if self.repeat {age.rem_euclid(self.curve.duration_s)}else{age};
        let s=self.curve.sample_seconds(t).map_err(|_|Error::InvalidArgument("invalid emission profile"))?;
        e.speed*=s.speed as f32;e.density_rate*=(s.amount*s.density) as f32;
        if !e.speed.is_finite()||!e.density_rate.is_finite()||e.speed<0. {return Err(Error::InvalidArgument("invalid evaluated emission profile"));}
        Ok(e)
    }
}

#[derive(Clone, Copy, Debug, Default)]
pub struct AdvanceReport {pub steps:u32,pub alpha:f64,pub dropped_seconds:f64,pub simulated_seconds:f64}
#[derive(Clone, Debug, Default)]
pub struct Clock {pub ticks:u64,pub accumulator:f64,pub dropped_total:f64}
impl Clock {
    pub fn plan(&self,elapsed:f64,cfg:&Config)->Result<(u32,f64,f64),Error> {
        if !elapsed.is_finite()||elapsed<0.||elapsed>3600. {return Err(Error::InvalidArgument("elapsed must be finite in 0..3600 seconds"));}
        let dt=cfg.fixed_dt as f64;let total=self.accumulator+elapsed;
        let wanted=((total+dt*1e-7)/dt).floor();let steps=wanted.min(cfg.max_substeps as f64) as u32;
        let dropped=(wanted-steps as f64).max(0.)*dt;
        let residual=(total-wanted*dt).clamp(0.,dt);
        Ok((steps,residual,dropped))
    }
}

/// Shared control plane. No grid allocation and no graphics-runtime dependency.
#[derive(Clone, Debug)]
pub struct Scene {
    pub emitters: Vec<Option<Emitter>>,
    pub profiles: Vec<Option<EmissionProfile>>,
    pub obstacles: Vec<Option<Obstacle>>,
}
impl Default for Scene {
    fn default() -> Self {
        Self { emitters: vec![None; MAX_EMITTERS], profiles: vec![None; MAX_EMITTERS],
               obstacles: vec![None; MAX_OBSTACLES] }
    }
}
impl Scene {
    pub fn set_emitter(&mut self, cfg: &Config, id: u32, emitter: Emitter) -> Result<(), Error> {
        let slot = self.emitters.get_mut(id as usize).ok_or(Error::InvalidArgument("emitter id out of range"))?;
        *slot = Some(emitter.validated(cfg)?); Ok(())
    }
    pub fn remove_emitter(&mut self, id: u32) -> Result<(), Error> {
        let slot = self.emitters.get_mut(id as usize).ok_or(Error::InvalidArgument("emitter id out of range"))?;
        *slot = None; self.profiles[id as usize] = None; Ok(())
    }
    pub fn set_profile(&mut self, id: u32, profile: Option<EmissionProfile>) -> Result<(), Error> {
        if self.emitters.get(id as usize).and_then(Option::as_ref).is_none() {
            return Err(Error::InvalidArgument("emitter not found"));
        }
        if profile.as_ref().is_some_and(|p| !p.start_time.is_finite()) {
            return Err(Error::InvalidArgument("invalid profile start time"));
        }
        self.profiles[id as usize] = profile; Ok(())
    }
    pub fn set_obstacle(&mut self, cfg: &Config, id: u32, obstacle: Obstacle) -> Result<(), Error> {
        let slot = self.obstacles.get_mut(id as usize).ok_or(Error::InvalidArgument("obstacle id out of range"))?;
        obstacle.validate(cfg)?; *slot = Some(obstacle); Ok(())
    }
    pub fn remove_obstacle(&mut self, id: u32) -> Result<(), Error> {
        *self.obstacles.get_mut(id as usize).ok_or(Error::InvalidArgument("obstacle id out of range"))? = None; Ok(())
    }
    pub fn sources(&self, cfg: &Config, time: f64) -> Result<[Option<Emitter>; MAX_EMITTERS], Error> {
        let mut out = std::array::from_fn(|_| None);
        for (id, emitter) in self.emitters.iter().enumerate() {
            if let Some(e) = emitter {
                let e = match &self.profiles[id] { Some(p) => p.apply(time, e)?, None => e.clone() };
                if e.speed > cfg.max_velocity || e.density_rate > 1e6 {
                    return Err(Error::InvalidArgument("profile exceeds source limits"));
                }
                out[id] = Some(e);
            }
        }
        Ok(out)
    }
}
