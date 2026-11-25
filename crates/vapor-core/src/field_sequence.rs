//! VPA1 time index and bounded two-keyframe VPF1 player. No simulation fallback.
use crate::{Error, fidelity::{FidelityGrid,FidelityFields},field_asset::{BakedField,crc32}};
use std::collections::VecDeque;
const HEADER:usize=64;const RECORD:usize=16;const MAX_FRAMES:usize=4096;
fn invalid(s:&'static str)->Error{Error::InvalidArgument(s)}
#[derive(Clone,Copy,Debug)]
pub struct FrameRecord {pub time:f64,pub bytes:u32,pub crc:u32}
pub struct SequenceIndex {grid:FidelityGrid,records:Vec<FrameRecord>}
impl SequenceIndex {
    pub fn decode(b:&[u8])->Result<Self,Error>{
        if b.len()<HEADER+RECORD||b.len()>HEADER+MAX_FRAMES*RECORD{return Err(invalid("invalid VPA index length"));}
        let u=|i:usize|u32::from_le_bytes(b[i..i+4].try_into().unwrap());
        let d=|i:usize|f64::from_le_bytes(b[i..i+8].try_into().unwrap());
        let count=u(8) as usize;
        if &b[..4]!=b"VPA1"||u(4)!=HEADER as u32||!(1..=MAX_FRAMES).contains(&count)||b.len()!=HEADER+count*RECORD||u(28)!=0||u(12)!=crc32(&b[16..]){return Err(invalid("invalid VPA header/checksum"));}
        let grid=FidelityGrid{cells:[u(16),u(20),u(24)],extent:[d(32),d(40),d(48)],density_cap:d(56)};let n=grid.count()?;
        let mut records=Vec::with_capacity(count);let mut prev=-1.;
        for i in 0..count {let p=HEADER+i*RECORD;let time=d(p);let bytes=u(p+8);let crc=u(p+12);
            if !time.is_finite()||time<0.||time>1e7||time<=prev||bytes as usize!=80+n*8{return Err(invalid("invalid VPA record"));}prev=time;records.push(FrameRecord{time,bytes,crc});}
        Ok(Self{grid,records})
    }
    pub fn grid(&self)->FidelityGrid{self.grid}
    pub fn records(&self)->&[FrameRecord]{&self.records}
}
pub fn frame_filename(i:usize)->Result<String,Error>{if i>=MAX_FRAMES{return Err(invalid("invalid VPA frame index"));}Ok(format!("frame_{i:04}.vpf"))}
pub struct FieldSequence {index:SequenceIndex,cache:VecDeque<(usize,BakedField)>}
impl FieldSequence {
    pub fn new(index:&[u8])->Result<Self,Error>{Ok(Self{index:SequenceIndex::decode(index)?,cache:VecDeque::new()})}
    pub fn index(&self)->&SequenceIndex{&self.index}
    pub fn cached_frames(&self)->usize{self.cache.len()}
    pub fn clear(&mut self){self.cache.clear();}
    fn frame(&mut self,i:usize,load:&mut impl FnMut(usize,usize)->Result<Vec<u8>,Error>)->Result<(),Error>{
        if let Some(p)=self.cache.iter().position(|(j,_)|*j==i){let f=self.cache.remove(p).unwrap();self.cache.push_back(f);return Ok(());}
        let r=self.index.records[i];let raw=load(i,r.bytes as usize)?;
        if raw.len()!=r.bytes as usize||crc32(&raw)!=r.crc{return Err(invalid("VPA frame length/checksum mismatch"));}
        let f=BakedField::decode(&raw)?;let g=self.index.grid;
        if f.grid.cells!=g.cells||f.grid.extent!=g.extent||f.grid.density_cap!=g.density_cap||f.time!=r.time{return Err(invalid("VPA frame metadata mismatch"));}
        if self.cache.len()==2{self.cache.pop_front();}self.cache.push_back((i,f));Ok(())
    }
    /// The caller's loader must bound I/O by the supplied exact byte length.
    /// Returns independent owned Float32 arrays; no references into the cache.
    pub fn sample(&mut self,time:f64,mut load:impl FnMut(usize,usize)->Result<Vec<u8>,Error>)->Result<BakedField,Error>{
        if !time.is_finite(){return Err(invalid("invalid sample time"));}
        let r=&self.index.records;let t=time.clamp(r[0].time,r[r.len()-1].time);let i=r.partition_point(|x|x.time<=t)-1;let exact=t==r[i].time;
        self.frame(i,&mut load)?;if !exact{self.frame(i+1,&mut load)?;}
        let a=&self.cache.iter().find(|(j,_)|*j==i).unwrap().1;
        let fields=if exact{a.fields.clone()}else{let b=&self.cache.iter().find(|(j,_)|*j==i+1).unwrap().1;let u=(t-a.time)/(b.time-a.time);
            let blend=|x:&[f32],y:&[f32]| x.iter().zip(y).map(|(&p,&q)|(p as f64+(q as f64-p as f64)*u) as f32).collect();
            FidelityFields{density:blend(&a.fields.density,&b.fields.density),temperature:blend(&a.fields.temperature,&b.fields.temperature)}};
        Ok(BakedField{grid:self.index.grid,time:t,fields})
    }
}
