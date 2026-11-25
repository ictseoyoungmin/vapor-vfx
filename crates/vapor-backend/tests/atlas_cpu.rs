//! Actual Rust CPU ticketed atlas contract, not a mock.
use vapor_backend::Engine;
use vapor_core::{Config,Emitter,Error};
fn scene()->Engine {
    let mut e=Engine::new(Config{cells:[8,10,8],cell_size:0.06,..Config::default()}).unwrap();
    e.set_emitter(0,Emitter{position:[0.24,0.14,0.24],direction:[0.,1.,0.],radius:0.07,length:0.09,speed:0.5,density_rate:20.,..Emitter::default()}).unwrap();e
}
#[test]
fn snapshot_is_at_submission_tick(){
    let mut e=scene();e.step_fixed(8).unwrap();
    let mut expected=vec![0;8*10*8*4];e.copy_atlas_rgba8(&mut expected).unwrap();
    assert!(expected.chunks_exact(4).any(|p|p[0]>0));
    let ticket=e.begin_atlas().unwrap().unwrap();assert_eq!(ticket.ticks,8);assert_eq!(ticket.bytes,expected.len());
    assert_eq!(e.begin_atlas().unwrap(),None);
    let mut short=[17u8;4];assert_eq!(e.poll_atlas(ticket.id,&mut short),Err(Error::BufferTooSmall));assert_eq!(short,[17;4]);
    e.step_fixed(3).unwrap();let mut out=vec![17;ticket.bytes];
    assert_eq!(e.poll_atlas(ticket.id,&mut out),Ok(true));assert_eq!(out,expected);
    assert_eq!(e.poll_atlas(ticket.id,&mut out),Err(Error::InvalidHandle));assert_eq!(out,expected);
    assert_eq!(e.metrics().unwrap().ticks,11);
}
#[test]
fn reset_cancel_and_id_monotonicity(){
    let mut e=scene();let a=e.begin_atlas().unwrap().unwrap();e.cancel_atlas(a.id).unwrap();
    assert_eq!(e.cancel_atlas(a.id),Err(Error::InvalidHandle));
    let b=e.begin_atlas().unwrap().unwrap();assert!(b.id>a.id);e.reset().unwrap();
    let mut out=vec![99;b.bytes];assert_eq!(e.poll_atlas(b.id,&mut out),Err(Error::InvalidHandle));assert!(out.iter().all(|&v|v==99));
    let c=e.begin_atlas().unwrap().unwrap();assert!(c.id>b.id);assert_eq!(c.ticks,0);assert_eq!(e.poll_atlas(c.id,&mut out),Ok(true));
    assert!(out.chunks_exact(4).all(|p|p==&[0,0,0,255]));
}
