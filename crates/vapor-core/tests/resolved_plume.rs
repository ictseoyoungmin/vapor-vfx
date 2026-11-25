//! Real Rust integration tests (must actually be run by cargo test).
use vapor_core::{Boundary, Config,Emitter,Field,Obstacle,ResolvedPlumeOptions,Simulation};
fn config()->Config {Config{cells:[12,16,12],cell_size:0.005,fixed_dt:0.004,max_velocity:3.,pressure_iterations:128,..Config::default()}}
fn emitter()->Emitter {Emitter{position:[0.03,0.018,0.03],radius:0.012,length:0.025,speed:0.35,density_rate:6.,temperature:1.,..Emitter::default()}}
#[test]
fn resolved_source_pressure_density_and_reset(){
    let mut s=Simulation::new_resolved_plume(config(),ResolvedPlumeOptions{seed_amplitude:0.05,seed_frequency_hz:2.}).unwrap();
    s.set_emitter(0,emitter()).unwrap();
    for _ in 0..12 {
        s.step_fixed(1).unwrap();let p=s.pressure_report().unwrap();let b=s.density_budget().unwrap();
        assert!(p.final_residual_rms<=(p.initial_divergence_rms*1e-4).max(1e-5));
        assert!(p.projected_divergence_rms.unwrap()<=(p.initial_divergence_rms*2e-4).max(2e-5));
        assert!(b.injected>0.&&b.residual.abs()<1e-10+1e-6*(b.before+b.injected));
    }
    let mut a=vec![0.;s.field_len(Field::Density)];s.copy_field(Field::Density,&mut a).unwrap();assert!(a.iter().any(|&v|v>0.));
    s.reset();assert!(s.pressure_report().is_none()&&s.density_budget().is_none());s.step_fixed(12).unwrap();let mut b=a.clone();s.copy_field(Field::Density,&mut b).unwrap();assert_eq!(a,b);
}
#[test]
fn reject_unsupported_and_unresolved_inputs(){
    assert!(Simulation::new_resolved_plume(Config{boundary:Boundary::Closed,..config()},ResolvedPlumeOptions::default()).is_err());
    assert!(Simulation::new_resolved_plume(config(),ResolvedPlumeOptions{seed_amplitude:0.2,seed_frequency_hz:1.}).is_err());
    let mut s=Simulation::new_resolved_plume(config(),ResolvedPlumeOptions::default()).unwrap();s.set_emitter(0,emitter()).unwrap();
    assert!(s.set_emitter(0,Emitter{radius:0.001,..emitter()}).is_err());assert_eq!(s.scene().emitters[0].as_ref().unwrap().radius,emitter().radius);
    assert!(s.set_obstacle(0,Obstacle::sphere([0.03,0.04,0.03],0.01)).is_err());
}
