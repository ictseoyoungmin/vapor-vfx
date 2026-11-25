//! VPF1 lossless data-only field interchange. No runtime fallback or provenance claim.
use crate::{Error,fidelity::{FidelityGrid,FidelityFields}};
const HEADER:usize=80;
const MAX:usize=2_097_152;
fn invalid(s:&'static str)->Error{Error::InvalidArgument(s)}
pub struct BakedField {pub grid:FidelityGrid,pub time:f64,pub fields:FidelityFields}
pub(crate) fn crc32(bytes:&[u8])->u32{
    let mut table=[0u32;256];for (i,c) in table.iter_mut().enumerate(){let mut v=i as u32;for _ in 0..8{v=(v>>1)^if v&1!=0{0xedb88320}else{0};}*c=v;}
    let mut c=0xffffffffu32;for &b in bytes{c=(c>>8)^table[((c^b as u32)&255) as usize];} !c
}
fn valid_time(t:f64)->bool{t.is_finite()&&(0.0..=1e7).contains(&t)}
fn validate(f:&BakedField)->Result<usize,Error>{
    let n=f.grid.count()?;if !valid_time(f.time)||f.fields.density.len()!=n||f.fields.temperature.len()!=n{return Err(invalid("invalid VPF field shape/time"));}
    if f.fields.density.iter().any(|&x|!x.is_finite()||x<0.0||x as f64>f.grid.density_cap*(1.0+1e-6))||f.fields.temperature.iter().any(|&x|!x.is_finite()||!(0.0..=1e5).contains(&x)){return Err(invalid("invalid VPF scalar"));} Ok(n)
}
impl BakedField {
    pub fn decode(bytes:&[u8])->Result<Self,Error>{
        if bytes.len()<HEADER||bytes.len()>HEADER+MAX*8{return Err(invalid("invalid VPF byte count"));}
        // All header reads are bounded by the fixed header check above.
        let u=|i:usize|u32::from_le_bytes(bytes[i..i+4].try_into().unwrap());
        let d=|i:usize|f64::from_le_bytes(bytes[i..i+8].try_into().unwrap());
        if &bytes[..4]!=b"VPF1"||u(4)!=HEADER as u32||u(20)!=0||u(68)!=0||u(76)!=0{return Err(invalid("unsupported VPF header"));}
        let grid=FidelityGrid{cells:[u(8),u(12),u(16)],extent:[d(24),d(32),d(40)],density_cap:d(48)};let n=grid.count()?;let time=d(56);
        if !valid_time(time)||bytes.len()!=HEADER+n*8||u(72) as usize!=n*8||u(64)!=crc32(&bytes[HEADER..]){return Err(invalid("invalid VPF payload length/CRC/time"));}
        let floats=|b:&[u8]|b.chunks_exact(4).map(|c|f32::from_le_bytes(c.try_into().unwrap())).collect::<Vec<_>>();
        let field=Self{grid,time,fields:FidelityFields{density:floats(&bytes[HEADER..HEADER+n*4]),temperature:floats(&bytes[HEADER+n*4..])}};validate(&field)?;Ok(field)
    }
    pub fn encode(&self)->Result<Vec<u8>,Error>{
        let n=validate(self)?;let mut b=Vec::with_capacity(HEADER+n*8);b.extend_from_slice(b"VPF1");b.extend_from_slice(&(HEADER as u32).to_le_bytes());
        for x in self.grid.cells{b.extend_from_slice(&x.to_le_bytes());}b.extend_from_slice(&0u32.to_le_bytes());
        for x in self.grid.extent{b.extend_from_slice(&x.to_le_bytes());}b.extend_from_slice(&self.grid.density_cap.to_le_bytes());b.extend_from_slice(&self.time.to_le_bytes());
        b.extend_from_slice(&[0u8;8]);b.extend_from_slice(&((n*8) as u32).to_le_bytes());b.extend_from_slice(&0u32.to_le_bytes());
        for &x in self.fields.density.iter().chain(self.fields.temperature.iter()){b.extend_from_slice(&x.to_le_bytes());}
        let crc=crc32(&b[HEADER..]);b[64..68].copy_from_slice(&crc.to_le_bytes());Ok(b)
    }
}
