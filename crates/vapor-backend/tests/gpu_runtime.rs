//! Real GPU test: no mock, CPU fallback, or skip-on-no-adapter inside the test.
//! Explicit opt-in command: cargo test -p vapor-backend --features gpu --test gpu_runtime -- --ignored --nocapture
#![cfg(all(feature="gpu",not(target_arch="wasm32")))]
use vapor_backend::{BackendOptions,Engine,Mode,ALLOW_SOFTWARE_GPU};
use vapor_core::{Config,Emitter,Field,Obstacle};
fn make(mode:Mode,scale:u32)->Engine {
    let c=Config{cells:[8,10,8],cell_size:0.06,pressure_iterations:64,..Config::default()};
    Engine::with_options(c,BackendOptions{mode,detail_scale:scale,flags:if std::env::var("VAPOR_ALLOW_SOFTWARE_GPU").as_deref()==Ok("1"){ALLOW_SOFTWARE_GPU}else{0},..BackendOptions::default()})
        .expect("A real wgpu adapter/device is required. CPU substitution is forbidden.")
}
fn field(e:&Engine,f:Field)->Vec<f32>{let mut out=vec![0.;e.field_len(f)];e.copy_field(f,&mut out).unwrap();out}
fn close(a:&[f32],b:&[f32],name:&str){assert_eq!(a.len(),b.len());let max=a.iter().zip(b).map(|(a,b)|(a-b).abs()).fold(0f32,f32::max);for (i,(&x,&y))in a.iter().zip(b).enumerate(){assert!(x.is_finite()&&y.is_finite());assert!((x-y).abs()<=0.003+0.002*x.abs().max(y.abs()),"{name}[{i}] CPU={x} GPU={y}, max_abs={max}");}println!("{name}: max_abs={max}");}
#[test]
#[ignore="requires an actual native wgpu adapter; CI explicitly runs this test"]
fn cpu_gpu_hybrid_representative_scene(){
    let mut cpu=make(Mode::Cpu,1);let mut gpu=make(Mode::Gpu,1);let mut hybrid=make(Mode::Hybrid,2);
    assert_eq!(gpu.info().active,Mode::Gpu);assert_eq!(hybrid.info().active,Mode::Hybrid);
    for s in [&mut cpu,&mut gpu,&mut hybrid]{s.step_fixed(2).unwrap();assert_eq!(s.metrics().unwrap().density_integral,0.);s.reset().unwrap();
        s.set_emitter(0,Emitter{position:[0.24,0.1,0.24],speed:0.6,density_rate:8.,..Emitter::default()}).unwrap();
        s.set_obstacle(0,Obstacle::sphere([0.24,0.34,0.24],0.06)).unwrap();s.step_fixed(8).unwrap();}
    for f in [Field::Density,Field::Temperature,Field::Pressure,Field::Velocity,Field::Solid]{let a=field(&cpu,f);close(&a,&field(&gpu,f),&format!("{f:?}"));assert_eq!(a,field(&hybrid,f),"hybrid must retain authoritative CPU coarse physics");}
    for s in [&cpu,&gpu,&hybrid]{let m=s.metrics().unwrap();assert_eq!(m.non_finite,0);assert!(m.density_integral>0.);assert!(m.max_density<=s.config().density_cap);let n=s.info().render_cells.iter().map(|&n|n as usize).product::<usize>();let mut atlas=vec![0;n*4];s.copy_atlas_rgba8(&mut atlas).unwrap();assert!(atlas.chunks_exact(4).all(|p|p[3]==255));assert!(atlas.chunks_exact(4).any(|p|p[0]>0));}
    assert_eq!(hybrid.info().render_cells,[16,20,16]);assert_eq!(hybrid.info().hybrid_upload_bytes,9*11*9*32);
    gpu.reset().unwrap();assert_eq!(gpu.metrics().unwrap().ticks,0);assert_eq!(gpu.metrics().unwrap().density_integral,0.);
    gpu.step_fixed(1).unwrap();assert!(gpu.metrics().unwrap().density_integral>0.);
    println!("CPU/GPU/hybrid representative runtime gate passed");
}

// Same actual GPU/Hybrid acceptance path; checks ordered GPU capture, cancellation and coexistence
// with the old synchronous readback buffer. No performance promise from submission timing.
#[test]
#[ignore="requires an actual native wgpu adapter; run explicitly"]
fn ticketed_atlas_preserves_submission_state(){
    use std::time::{Duration,Instant};
    use vapor_core::Error;
    for (mode,scale) in [(Mode::Gpu,1),(Mode::Hybrid,2)]{
        let mut e=make(mode,scale);
        e.set_emitter(0,Emitter{position:[0.24,0.1,0.24],speed:0.6,density_rate:12.,..Emitter::default()}).unwrap();e.step_fixed(8).unwrap();
        let mut expected=vec![0;e.info().render_cells.iter().map(|&x|x as usize).product::<usize>()*4];
        e.copy_atlas_rgba8(&mut expected).unwrap();assert!(expected.chunks_exact(4).any(|p|p[0]>0));
        let a=e.begin_atlas().unwrap().unwrap();assert_eq!(a.ticks,8);assert_eq!(e.begin_atlas().unwrap(),None);
        e.step_fixed(2).unwrap();let mut later=vec![0;expected.len()];e.copy_atlas_rgba8(&mut later).unwrap();
        let mut out=vec![37;expected.len()];let deadline=Instant::now()+Duration::from_secs(35);
        loop{if e.poll_atlas(a.id,&mut out).unwrap(){break;}assert!(out.iter().all(|&x|x==37));assert!(Instant::now()<deadline);std::thread::sleep(Duration::from_millis(1));}
        assert_eq!(out,expected);assert_eq!(e.poll_atlas(a.id,&mut out),Err(Error::InvalidHandle));
        let b=e.begin_atlas().unwrap().unwrap();assert!(b.id>a.id);e.cancel_atlas(b.id).unwrap();
        let c=e.begin_atlas().unwrap().unwrap();assert!(c.id>b.id);e.reset().unwrap();assert_eq!(e.poll_atlas(c.id,&mut out),Err(Error::InvalidHandle));
        let d=e.begin_atlas().unwrap().unwrap();let deadline=Instant::now()+Duration::from_secs(35);
        loop{if e.poll_atlas(d.id,&mut out).unwrap(){break;}assert!(Instant::now()<deadline);std::thread::sleep(Duration::from_millis(1));}
        assert!(out.chunks_exact(4).all(|p|p==[0,0,0,255]));
    }
}
