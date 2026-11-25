//! CPU fidelity path ported from bindings/web/fidelity.mjs (0.15).
//! Local coordinates, x-fastest Float32 fields; f64 arithmetic matches the JS reference.
//! This is a game-art density generator, not a meteorological model.
use crate::Error;
pub type Vec3 = [f64;3];
const LIMIT:usize=2_097_152;
fn invalid(s:&'static str)->Error { Error::InvalidArgument(s) }
fn bounded(v:f64,lo:f64,hi:f64)->bool { v.is_finite() && v>=lo && v<=hi }
fn sat(v:f64)->f64 {v.clamp(0.0,1.0)}
fn lerp(a:f64,b:f64,t:f64)->f64 {a+(b-a)*t}
fn smooth(a:f64,b:f64,x:f64)->f64 {let t=sat((x-a)/(b-a));t*t*(3.0-2.0*t)}
fn quintic(t:f64)->f64 {t*t*t*(t*(t*6.0-15.0)+10.0)}
#[derive(Clone,Copy,Debug)]
pub struct FidelityGrid { pub cells:[u32;3], pub extent:Vec3, pub density_cap:f64 }
impl FidelityGrid {
    pub fn count(&self)->Result<usize,Error> {
        if self.cells.iter().any(|&v| !(4..=512).contains(&v)) || self.extent.iter().any(|&v| !bounded(v,0.0001,1e7)) || !bounded(self.density_cap,0.00001,100.0) {return Err(invalid("invalid fidelity grid"));}
        let n=self.cells.iter().try_fold(1usize, |p,&v| p.checked_mul(v as usize)).ok_or(Error::Capacity)?;
        if n>LIMIT {return Err(Error::Capacity);} Ok(n)
    }
    fn dims(&self)->[usize;3] {self.cells.map(|n|n as usize)}
}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
#[repr(u32)]
pub enum VolumeKind { Cloud=1, Fog=2, Dust=3 }
#[derive(Clone,Copy,Debug)]
pub struct DensitySettings { pub seed:u32,pub coverage:f64,pub humidity:f64,pub erosion:f64,pub wind:Vec3 }
#[derive(Clone,Debug)]
pub struct FidelityFields {pub density:Vec<f32>,pub temperature:Vec<f32>}
fn hash(x:i32,y:i32,z:i32,seed:u32)->u32 {
    let mut h=seed^(x as u32).wrapping_mul(0x9e3779b1)^(y as u32).wrapping_mul(0x85ebca77)^(z as u32).wrapping_mul(0xc2b2ae3d);
    h=(h^(h>>16)).wrapping_mul(0x7feb352d);h=(h^(h>>15)).wrapping_mul(0x846ca68b);h^(h>>16)
}
fn rand(x:i32,y:i32,z:i32,s:u32)->f64 {hash(x,y,z,s) as f64/4294967296.0}
fn grad(h:u32,x:f64,y:f64,z:f64)->f64 {
    let h=h&15;let u=if h<8{x}else{y};let v=if h<4{y}else if h==12||h==14{x}else{z};
    (if h&1!=0{-u}else{u})+(if h&2!=0{-v}else{v})
}
fn perlin(x:f64,y:f64,z:f64,s:u32,p:i32)->f64 {
    let [ix,iy,iz]=[x,y,z].map(|v|v.floor() as i32);
    let [fx,fy,fz]=[x-ix as f64,y-iy as f64,z-iz as f64];let [u,v,w]=[fx,fy,fz].map(quintic);
    let h=|a:i32,b:i32,c:i32| grad(hash((ix+a).rem_euclid(p),(iy+b).rem_euclid(p),(iz+c).rem_euclid(p),s),fx-a as f64,fy-b as f64,fz-c as f64);
    sat(0.5+0.5*lerp(lerp(lerp(h(0,0,0),h(1,0,0),u),lerp(h(0,1,0),h(1,1,0),u),v),lerp(lerp(h(0,0,1),h(1,0,1),u),lerp(h(0,1,1),h(1,1,1),u),v),w))
}
fn worley(x:f64,y:f64,z:f64,s:u32,p:i32)->f64 {
    let [ix,iy,iz]=[x,y,z].map(|v|v.floor() as i32);let mut d=f64::INFINITY;
    for k in -1..=1 {for j in -1..=1 {for i in -1..=1 {
        let (a,b,c)=(ix+i,iy+j,iz+k);let h=hash(a.rem_euclid(p),b.rem_euclid(p),c.rem_euclid(p),s);
        let dx=a as f64+0.08+0.84*(h&1023) as f64/1023.0-x;
        let dy=b as f64+0.08+0.84*((h>>10)&1023) as f64/1023.0-y;
        let dz=c as f64+0.08+0.84*((h>>20)&1023) as f64/1023.0-z;
        d=d.min(dx*dx+dy*dy+dz*dz);
    }}} 1.0-sat(d.sqrt()/1.12)
}
const N:usize=40;
struct NoiseTiles { p:Vec<f32>,w:Vec<f32> }
impl NoiseTiles {
    fn new(seed:u32)->Self {
        let mut p=Vec::with_capacity(N*N*N);let mut w=Vec::with_capacity(N*N*N);
        for z in 0..N {for y in 0..N {for x in 0..N {
            let [a,b,c]=[x,y,z].map(|v|v as f64*5.0/N as f64);
            p.push(perlin(a,b,c,seed,5) as f32);w.push(worley(a,b,c,seed^0x45b9f1,5) as f32);
        }}} Self{p,w}
    }
    fn sample(field:&[f32],x:f64,y:f64,z:f64)->f64 {
        let [x,y,z]=[x,y,z].map(|a| {let t=a/5.0;(t-t.floor())*N as f64});
        let [i,j,k]=[x,y,z].map(|a|a.floor() as usize);let [u,v,w]=[x-i as f64,y-j as f64,z-k as f64];
        let a=|dx:usize,dy:usize,dz:usize| field[(i+dx)%N+N*((j+dy)%N+N*((k+dz)%N))] as f64;
        lerp(lerp(lerp(a(0,0,0),a(1,0,0),u),lerp(a(0,1,0),a(1,1,0),u),v),lerp(lerp(a(0,0,1),a(1,0,1),u),lerp(a(0,1,1),a(1,1,1),u),v),w)
    }
}
fn terrain_at(terrain:Option<&[f32]>,dims:[usize;3],x:f64,z:f64)->f64 {
    let Some(t)=terrain else{return 0.0;}; let [nx,_,nz]=dims;
    let a=(x*nx as f64-0.5).clamp(0.0,(nx-1) as f64);let b=(z*nz as f64-0.5).clamp(0.0,(nz-1) as f64);
    let (i,j)=(a.floor() as usize,b.floor() as usize);let (u,v)=(a-i as f64,b-j as f64);let di=if i<nx-1{1}else{0};let dj=if j<nz-1{nx}else{0};let k=i+j*nx;
    lerp(lerp(t[k] as f64,t[k+di] as f64,u),lerp(t[k+dj] as f64,t[k+dj+di] as f64,u),v)
}
/// Reusable seed-specific periodic tiles. No hidden global cache or lock.
pub struct FidelityGenerator {seed:u32,tiles:NoiseTiles}
impl FidelityGenerator {
    pub fn new(seed:u32)->Self {Self{seed,tiles:NoiseTiles::new(seed)}}
    /// `terrain`: optional x-fastest XZ height map in metres, local to volume.
    pub fn generate(&self,grid:FidelityGrid,kind:VolumeKind,s:DensitySettings,time:f64,terrain:Option<&[f32]>)->Result<FidelityFields,Error> {
        let count=grid.count()?;let [nx,ny,nz]=grid.dims();let extent=grid.extent;let cloud=kind==VolumeKind::Cloud;
        if self.seed!=s.seed || ![s.coverage,s.humidity,s.erosion].iter().all(|&v|bounded(v,0.0,1.0)) || !s.wind.iter().all(|&v|bounded(v,-100.0,100.0)) || !bounded(time,0.0,1e7) {return Err(invalid("invalid fidelity settings"));}
        if let Some(t)=terrain {if cloud||t.len()!=nx*nz||t.iter().any(|&v|!v.is_finite()||v<0.0||v as f64>=extent[1]) {return Err(invalid("invalid fidelity terrain"));}}
        let p=|x,y,z| NoiseTiles::sample(&self.tiles.p,x,y,z);let w=|x,y,z| NoiseTiles::sample(&self.tiles.w,x,y,z);
        let shift:[f64;3]=std::array::from_fn(|i|(s.wind[i]*time/extent[i])%5.0);
        let (coverage,humidity,erosion)=(s.coverage,s.humidity,s.erosion);let mut thermals=[[0.0;5];8];
        if cloud {for (i,t) in thermals.iter_mut().enumerate() {let u=i as f64/7.0;let i=i as i32;let seed=s.seed;
            let px=0.17+0.66*u+(rand(i,1,0,seed)-0.5)*0.055;let pz=0.5+(rand(i,2,0,seed)-0.5)*0.24;
            let core=(0.60*(-((u-0.23)/0.22).powi(2)).exp()).max((-((u-0.62)/0.26).powi(2)).exp());
            *t=[px,pz,0.29+0.49*core+0.13*rand(i,3,0,seed),0.105+0.070*rand(i,4,0,seed),0.16+0.12*rand(i,5,0,seed)];
        }}
        let mut density=vec![0.0f32;count];
        for z in 0..nz {for y in 0..ny {for x in 0..nx {
            let (x0,y0,z0)=((x as f64+0.5)/nx as f64,(y as f64+0.5)/ny as f64,(z as f64+0.5)/nz as f64);
            let (xx,yy,zz)=(x0-shift[0],y0-shift[1],z0-shift[2]);
            let rho=if cloud {
                let low=p(xx*4.2+2.7,yy*2.8+0.2,zz*4.2+1.1);
                let wx=x0+0.055*(p(xx*5.0+1.0,yy*5.0+2.0,zz*5.0)-0.5);let wz=z0+0.070*(p(xx*4.0,yy*4.0-1.0,zz*4.0+2.0)-0.5);let wy=y0+0.045*(low-0.5);
                let mut shape=-1.0f64;
                for [cx,cz,h,rx,rz] in thermals {let base=0.16;let half=(h-base)*0.5;let center=base+half;let d=(((wx-cx)/rx).powi(2)+((wy-center)/half).powi(2)+((wz-cz)/rz).powi(2)).sqrt();shape=shape.max((1.0-d)*rx.min(half).min(rz)*5.0);}
                let skirt=1.0-(((wx-0.5)/0.43).powi(2)+((wy-0.27)/0.15).powi(2)+((wz-0.5)/0.35).powi(2)).sqrt();shape=shape.max(skirt*0.65);if shape< -0.38 {continue;}
                let a=w(xx*9.2,yy*5.4,zz*7.2);let b=w(xx*18.4+1.8,yy*10.8+0.4,zz*14.4+1.1);let c=w(xx*38.0+2.6,yy*23.0+3.1,zz*29.0+2.3);let d=p(xx*57.0,yy*36.0+1.0,zz*43.0);
                let billow=0.76*(a-0.42)+0.38*(b-0.43)+0.20*(c-0.43)+0.13*(d-0.5)+0.23*(low-0.5);
                let weather=(coverage-0.53)*0.38+(humidity-0.76)*0.24;let edge=shape+billow+weather-0.10*erosion;
                let base=smooth(0.125,0.17,y0)*(1.0-smooth(0.91,0.99,y0));let rho=smooth(-0.028,0.09,edge)*base*(0.60+0.40*smooth(0.12,0.52,edge))*(0.67+0.33*humidity);
                let border=smooth(0.0,0.08,x0)*(1.0-smooth(0.92,1.0,x0))*smooth(0.0,0.08,z0)*(1.0-smooth(0.92,1.0,z0));sat(rho*border)
            }else{
                let h=(y0*extent[1]-terrain_at(terrain,[nx,ny,nz],x0,z0))/extent[1];if h<=0.0||h>0.65{continue;}
                let wx=xx+0.12*(p(xx*4.0,yy*2.0,zz*4.0)-0.5);let wz=zz+0.10*(p(xx*4.0+2.0,yy*3.0,zz*4.0+1.0)-0.5);
                let bands=0.52*p(wx*5.0,yy*11.0,wz*5.0)+0.30*w(wx*10.0+1.0,yy*15.0,wz*10.0)+0.18*p(wx*24.0,yy*30.0,wz*24.0+2.0);
                let weather=p(xx*2.8,0.7,zz*2.8+1.0);let height=(if kind==VolumeKind::Dust{0.19}else{0.12})*(0.6+1.25*weather)*(0.6+0.6*humidity);
                let layer=(-h/height).exp()*(1.0-smooth(height*1.6,height*3.8,h));let pockets=smooth(0.22,0.73,bands+(coverage-0.55)*0.48+(humidity-0.7)*0.20-erosion*0.1);
                let border=smooth(0.0,0.10,x0)*(1.0-smooth(0.90,1.0,x0))*smooth(0.0,0.10,z0)*(1.0-smooth(0.90,1.0,z0));sat(layer*pockets*border*smooth(0.0,0.018,h)*(0.76+0.24*weather))
            };density[x+nx*(y+ny*z)]=(rho*grid.density_cap) as f32;
        }}}
        Ok(FidelityFields{density,temperature:vec![0.0;count]})
    }
}

// Shared optical model: directional light, sky/ground, bounded multiple-scatter
// approximation, linear scene composition. Local light and temporal accumulation
// are intentionally outside this initial CPU port.
#[derive(Clone,Copy,Debug)]
pub struct OpticalMaterial {pub colour:Vec3,pub extinction:f64,pub anisotropy:f64,pub albedo:f64,pub emission:f64,pub thermal_fade:f64,pub ambient:f64}
#[derive(Clone,Copy,Debug)]
pub struct FidelityLighting {pub direction:Vec3,pub radiance:Vec3,pub sky:Vec3,pub ground:Vec3,pub multi_scatter:f64,pub shadow_steps:u32,pub light_scale:f64}
#[derive(Clone,Copy,Debug)]
pub struct FidelityCamera {pub eye:Vec3,pub target:Vec3,pub width:u32,pub height:u32,pub steps:u32,pub fov:f64,pub exposure:f64,pub jitter:f64,pub dark:bool}
pub struct Scene<'a> {pub depth:&'a[f32],pub radiance:&'a[f32]}
pub struct FidelityFrame {pub rgba:Vec<u8>,pub linear:Vec<f32>,pub alpha:Vec<f32>}
fn dot(a:Vec3,b:Vec3)->f64 {a[0]*b[0]+a[1]*b[1]+a[2]*b[2]}
fn cross(a:Vec3,b:Vec3)->Vec3 {[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]}
fn norm(a:Vec3)->Result<Vec3,Error>{let l=a[0].hypot(a[1]).hypot(a[2]);if !l.is_finite()||l<=1e-9{return Err(invalid("degenerate vector"));}Ok(a.map(|v|v/l))}
fn sample(a:&[f32],dims:[usize;3],p:Vec3)->f64 {
    if p.iter().any(|&x|!(0.0..=1.0).contains(&x)){return 0.0;}
    let q:[f64;3]=std::array::from_fn(|i|(p[i]*dims[i] as f64-0.5).clamp(0.0,(dims[i]-1) as f64));
    let [i,j,k]=q.map(|x|x.floor() as usize);let [nx,ny,nz]=dims;let (u,v,w)=(q[0]-i as f64,q[1]-j as f64,q[2]-k as f64);
    let f=|x:usize,y:usize,z:usize|a[(i+x).min(nx-1)+nx*((j+y).min(ny-1)+ny*(k+z).min(nz-1))] as f64;
    lerp(lerp(lerp(f(0,0,0),f(1,0,0),u),lerp(f(0,1,0),f(1,1,0),u),v),lerp(lerp(f(0,0,1),f(1,0,1),u),lerp(f(0,1,1),f(1,1,1),u),v),w)
}
fn exit(p:f64,d:f64)->f64{if d>1e-12{(1.0-p)/d}else if d< -1e-12{-p/d}else{f64::INFINITY}}
fn hg(g:f64,c:f64)->f64{(1.0-g*g)/(1.0+g*g-2.0*g*c).max(1e-5).powf(1.5)}
fn phase(g:f64,c:f64)->f64{0.88*hg(g,c)+0.12*hg(-g*0.38,c)}
fn display(x:f64,exposure:f64)->u8 {let v=(x*exposure).max(0.0);let x=(v*(2.51*v+0.03))/(v*(2.43*v+0.59)+0.14);(255.0*sat(if x<=0.0031308{12.92*x}else{1.055*x.powf(1.0/2.4)-0.055})).round() as u8}
fn sky_radiance(d:Vec3,sun:Vec3,dark:bool)->Vec3 {
    if dark{return [0.004,0.006,0.010];}let h=(1.0-sat(d[1]*1.6)).powi(3);let g=dot(d,sun).max(0.0).powi(24)*0.14;
    [lerp(0.035,0.15,h)+g,lerp(0.105,0.27,h)+g*0.83,lerp(0.34,0.48,h)+g*0.55]
}
pub struct FidelityRenderer {grid:FidelityGrid,m:OpticalMaterial,l:FidelityLighting,fields:FidelityFields,lc:[usize;3],optical:Vec<f32>,up:Vec<f32>,down:Vec<f32>}
impl FidelityRenderer {
    /// Prepare a reusable lighting cache from an owned snapshot. Camera changes do not rebuild it.
    pub fn prepare(grid:FidelityGrid,mut fields:FidelityFields,m:OpticalMaterial,mut l:FidelityLighting)->Result<Self,Error>{
        let count=grid.count()?;let dims=grid.dims();let extent=grid.extent;
        if fields.density.len()!=count||fields.temperature.len()!=count||m.colour.iter().any(|&x|!bounded(x,0.0,1.0))||!bounded(m.extinction,0.0,1000.0)||!bounded(m.anisotropy,-0.9,0.9)||!bounded(m.albedo,0.0,1.0)||!bounded(m.emission,0.0,10.0)||!bounded(m.thermal_fade,0.0,1.0)||!bounded(m.ambient,0.0,1.0){return Err(invalid("invalid fidelity material/fields"));}
        if l.radiance.iter().chain(l.sky.iter()).chain(l.ground.iter()).any(|&x|!bounded(x,0.0,50.0))||!bounded(l.multi_scatter,0.0,1.0)||!bounded(l.light_scale,0.125,1.0)||!(4..=64).contains(&l.shadow_steps){return Err(invalid("invalid fidelity lighting"));}
        l.direction=norm(l.direction)?;
        for (rho,&heat) in fields.density.iter_mut().zip(&fields.temperature){if !bounded(*rho as f64,0.0,grid.density_cap*(1.0+1e-6))||!bounded(heat as f64,0.0,1e5){return Err(invalid("invalid density/temperature"));}*rho=(*rho as f64*(1.0-m.thermal_fade*(1.0-(-(heat as f64)).exp()))) as f32;}
        let lc=dims.map(|n|((n as f64*l.light_scale).ceil() as usize).max(4));let [nx,ny,nz]=lc;let n=nx*ny*nz;
        if n*l.shadow_steps as usize>64_000_000{return Err(Error::Capacity);}
        let mut optical=vec![0.0f32;n];let mut up=optical.clone();let mut down=optical.clone();
        let sun:Vec3=std::array::from_fn(|i|l.direction[i]/extent[i]);let s=|p|sample(&fields.density,dims,p);
        for z in 0..nz{for x in 0..nx{
            let mut running=0.0;for y in (0..ny).rev(){let i=x+nx*(y+ny*z);let p=[(x as f64+0.5)/nx as f64,(y as f64+0.5)/ny as f64,(z as f64+0.5)/nz as f64];let delta=s(p)*extent[1]/ny as f64*m.extinction;up[i]=(running+0.5*delta) as f32;running+=delta;
                let len=(0..3).map(|a|exit(p[a],sun[a])).fold(f64::INFINITY,f64::min);if len>0.0&&len.is_finite(){let step=len/l.shadow_steps as f64;let mut sum=0.0;for j in 0..l.shadow_steps{let t=(j as f64+0.5)*step;sum+=s(std::array::from_fn(|a|p[a]+sun[a]*t));}optical[i]=(sum*step*m.extinction) as f32;}
            }
            running=0.0;for y in 0..ny{let i=x+nx*(y+ny*z);let delta=s([(x as f64+0.5)/nx as f64,(y as f64+0.5)/ny as f64,(z as f64+0.5)/nz as f64])*extent[1]/ny as f64*m.extinction;down[i]=(running+0.5*delta) as f32;running+=delta;}
        }}Ok(Self{grid,m,l,fields,lc,optical,up,down})
    }
    pub fn render(&self,c:FidelityCamera,scene:Option<Scene<'_>>)->Result<FidelityFrame,Error>{
        if !(1..=1600).contains(&c.width)||!(1..=1600).contains(&c.height)||!(8..=512).contains(&c.steps)||!bounded(c.fov,10.0,110.0)||!bounded(c.exposure,0.01,20.0)||!bounded(c.jitter,0.0,1.0)||c.eye.iter().chain(c.target.iter()).any(|v|!v.is_finite()||v.abs()>1e9){return Err(invalid("invalid fidelity camera"));}
        let pixels=c.width as usize*c.height as usize;if pixels*c.steps as usize>180_000_000{return Err(Error::Capacity);}
        if let Some(ref s)=scene{if s.depth.len()!=pixels||s.radiance.len()!=pixels*3||s.depth.iter().any(|&x|!x.is_finite()||x<0.0)||s.radiance.iter().any(|&x|!bounded(x as f64,0.0,100.0)){return Err(invalid("invalid fidelity scene"));}}
        let f=norm(std::array::from_fn(|i|c.target[i]-c.eye[i]))?;let r=norm(cross(f,if f[1].abs()>0.99{[0.0,0.0,1.0]}else{[0.0,1.0,0.0]}))?;let u=cross(r,f);let half=(c.fov*std::f64::consts::PI/360.0).tan();let aspect=c.width as f64/c.height as f64;
        let mut out=FidelityFrame{rgba:vec![0;pixels*4],linear:vec![0.0;pixels*3],alpha:vec![0.0;pixels]};let e=self.grid.extent;let dims=self.grid.dims();let m=self.m;let l=self.l;
        for y in 0..c.height{for x in 0..c.width{let i=x as usize+c.width as usize*y as usize;
            let a=(2.0*(x as f64+0.5)/c.width as f64-1.0)*half*aspect;let b=(1.0-2.0*(y as f64+0.5)/c.height as f64)*half;let d=norm(std::array::from_fn(|j|f[j]+a*r[j]+b*u[j]))?;
            let mut near=0.0f64;let mut far=f64::INFINITY;for j in 0..3{if d[j].abs()<1e-9{if c.eye[j]<0.0||c.eye[j]>e[j]{far=-1.0;break;}}else{let a=-c.eye[j]/d[j];let b=(e[j]-c.eye[j])/d[j];near=near.max(a.min(b));far=far.min(a.max(b));}}
            let bg=match &scene{Some(s)=>{if s.depth[i]>0.0{far=far.min(s.depth[i] as f64);}std::array::from_fn(|k|s.radiance[3*i+k] as f64)},None=>sky_radiance(d,l.direction,c.dark)};
            let mut trans=1.0f64;let mut col=[0.0f64;3];let cos=dot(d,l.direction);let (p1,p2,p3)=(phase(m.anisotropy,cos),phase(m.anisotropy*0.43,cos),phase(m.anisotropy*0.15,cos));
            if far>near{let dt=(far-near)/c.steps as f64;for j in 0..c.steps{if trans<=0.0007{break;}let t=near+(j as f64+c.jitter)*dt;let p=std::array::from_fn(|k|(c.eye[k]+d[k]*t)/e[k]);let rho=sample(&self.fields.density,dims,p);if rho<=1e-7{continue;}
                let opacity=-(-rho*m.extinction*dt).exp_m1();let weight=trans*opacity;let (od,ou,og)=(sample(&self.optical,self.lc,p),sample(&self.up,self.lc,p),sample(&self.down,self.lc,p));let direct=(-od).exp()*p1;
                let scatter=l.multi_scatter*(0.50*m.albedo*(-0.33*od).exp()*p2+0.23*m.albedo*m.albedo*(-0.10*od).exp()*p3);let sky=0.20*(-0.09*ou).exp()+0.80*(-0.65*ou).exp();let ground=(-0.23*og).exp();let env=m.ambient*0.30;
                let emission=if m.emission>0.0{sat(sample(&self.fields.temperature,dims,p)/5.0).powi(2)*m.emission}else{0.0};
                for k in 0..3{let light=l.radiance[k]*(direct+scatter)+l.sky[k]*(sky+env)+l.ground[k]*ground;col[k]+=weight*(m.colour[k]*m.albedo*light+emission*[1.0,0.30,0.045][k]);}trans*=1.0-opacity;
            }}
            out.alpha[i]=(1.0-trans) as f32;for k in 0..3{let value=(col[k]+trans*bg[k]) as f32;out.linear[3*i+k]=value;out.rgba[4*i+k]=display(value as f64,c.exposure);}out.rgba[4*i+3]=255;
        }}Ok(out)
    }
}
