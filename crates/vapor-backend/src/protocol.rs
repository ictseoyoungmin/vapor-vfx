//! Wire layout shared by native wgpu and browser WebGPU; explicit LE encoding, no transmute.
use vapor_core::{Config, Error, Scene, Shape};
use vapor_core::solver::Cell;

pub const PARAM_BYTES: usize = 128;
pub const CONTROL_BYTES: usize = 32 * 48 * 2;
pub const CELL_BYTES: usize = 32;
pub const WORKGROUP: u32 = 64;
pub const MAIN_SHADER: &str = include_str!("../../../shaders/compute/mac.wgsl");
pub const DETAIL_SHADER: &str = include_str!("../../../shaders/compute/detail.wgsl");
pub const EXPORT_SHADER: &str = include_str!("../../../shaders/compute/export.wgsl");

pub fn parameters(c: &Config, scale: u32) -> Vec<u8> {
    let mut out = Vec::with_capacity(PARAM_BYTES);
    for v in [c.cells[0],c.cells[1],c.cells[2],c.padded_len().unwrap() as u32] { put_u32(&mut out,v); }
    for v in [c.origin[0],c.origin[1],c.origin[2],c.cell_size,c.fixed_dt,c.density_decay,c.cooling,c.buoyancy,
              c.density_weight,c.drag,c.vorticity,c.max_velocity,c.wind[0],c.wind[1],c.wind[2],c.density_cap,
              c.sor_omega,0.,0.,0.] { put_f32(&mut out,v); }
    for v in [32,32,c.boundary as u32,0,scale,c.cells[0]*scale,c.cells[1]*scale,c.cells[2]*scale] { put_u32(&mut out,v); }
    debug_assert_eq!(out.len(),PARAM_BYTES); out
}
pub fn controls(c:&Config, scene:&Scene, time:f64) -> Result<Vec<u8>,Error> {
    let mut out=Vec::with_capacity(CONTROL_BYTES);
    for e in scene.sources(c,time)? {
        let values = match e {
            Some(e) => [e.position[0],e.position[1],e.position[2],e.radius,
                        e.direction[0],e.direction[1],e.direction[2],e.length,
                        e.speed,e.density_rate,e.temperature,if e.enabled {1.}else{0.}],
            None => [0.;12],
        };
        for x in values { put_f32(&mut out,x); }
    }
    for o in &scene.obstacles {
        let values = match o {
            Some(o) => {
                let (a,b,r,kind)=match o.shape {Shape::Capsule{a,b,radius}=>(a,b,radius,0.),Shape::Box{min,max}=>(min,max,0.,1.)};
                [a[0],a[1],a[2],r,b[0],b[1],b[2],kind,o.velocity[0],o.velocity[1],o.velocity[2],if o.enabled {1.}else{0.}]
            }, None => [0.;12],
        };
        for x in values {put_f32(&mut out,x);}
    }
    debug_assert_eq!(out.len(),CONTROL_BYTES); Ok(out)
}
pub fn encode_cells(cells:&[Cell]) -> Vec<u8> {
    let mut out=Vec::with_capacity(cells.len()*CELL_BYTES);
    for c in cells {for &v in c.v.iter().chain(c.s.iter()) {put_f32(&mut out,v);}} out
}
pub fn decode_cells(bytes:&[u8]) -> Result<Vec<Cell>,Error> {
    if bytes.len()%CELL_BYTES!=0 {return Err(Error::InvalidArgument("invalid MAC byte length"));}
    let mut out=Vec::with_capacity(bytes.len()/CELL_BYTES);
    for c in bytes.chunks_exact(CELL_BYTES) {
        let f:Vec<f32>=c.chunks_exact(4).map(|b|f32::from_le_bytes(b.try_into().unwrap())).collect();
        if f.iter().any(|v|!v.is_finite()){return Err(Error::NonFiniteState);}
        out.push(Cell{v:f[..4].try_into().unwrap(),s:f[4..].try_into().unwrap()});
    } Ok(out)
}
fn put_u32(out:&mut Vec<u8>,v:u32){out.extend_from_slice(&v.to_le_bytes());}
fn put_f32(out:&mut Vec<u8>,v:f32){out.extend_from_slice(&v.to_le_bytes());}

#[cfg(test)] mod tests {
    use super::*;
    #[test] fn layouts(){let c=Config::default();assert_eq!(parameters(&c,2).len(),128);assert_eq!(controls(&c,&Scene::default(),0.).unwrap().len(),3072);}
    #[test] fn mac_roundtrip(){let cells=[Cell{v:[1.,2.,3.,0.],s:[4.,5.,6.,0.]}];let bytes=encode_cells(&cells);assert_eq!(bytes.len(),32);let out=decode_cells(&bytes).unwrap();assert_eq!(out[0].v,cells[0].v);assert_eq!(out[0].s,cells[0].s);}
    #[test] fn rejects_nan(){assert!(decode_cells(&[0;31]).is_err());let mut b=vec![0;32];b[..4].copy_from_slice(&f32::NAN.to_le_bytes());assert!(decode_cells(&b).is_err());}
}
