//! Real Rust CPU numerical tests. No GPU, fixtures, or alternative solver.
use vapor_core::{Boundary,Config,Emitter,Field,Simulation};
use vapor_core::runtime::Clock;
use vapor_core::solver::Cell;
fn config()->Config {Config {cells:[6,8,6],cell_size:0.1,boundary:Boundary::Closed,
    buoyancy:0.,density_weight:0.,vorticity:0.,drag:0.,pressure_iterations:80,..Config::default()}}
fn at(x:usize,y:usize,z:usize,c:&Config)->usize {x+(c.cells[0] as usize+1)*(y+(c.cells[1] as usize+1)*z)}
fn field(sim:&Simulation,f:Field)->Vec<f32> {let mut out=vec![0.;sim.field_len(f)];sim.copy_field(f,&mut out).unwrap();out}
#[test]
fn motionless_scalar_decay_matches_analytic_solution() {
    let cfg=config();let mut sim=Simulation::new(cfg.clone()).unwrap();
    let mut cells=vec![Cell::default();cfg.padded_len().unwrap()];
    for z in 0..cfg.cells[2] as usize {for y in 0..cfg.cells[1] as usize {for x in 0..cfg.cells[0] as usize {
        cells[at(x,y,z,&cfg)].s=[1.5,2.0,0.,0.];
    }}}
    sim.import_mac(&cells,&vec![[0.;4];cells.len()],Clock::default(),0).unwrap();sim.step_fixed(60).unwrap();
    let rho=1.5*(-cfg.density_decay*cfg.fixed_dt*60.).exp();let temp=2.*(-cfg.cooling*cfg.fixed_dt*60.).exp();
    for v in field(&sim,Field::Density) {assert!((v-rho).abs()<2e-5,"density {v} != {rho}");}
    for v in field(&sim,Field::Temperature) {assert!((v-temp).abs()<2e-5,"temperature {v} != {temp}");}
    assert_eq!(sim.metrics().max_speed,0.);assert_eq!(sim.metrics().clamped_velocities,0);
}
#[test]
fn stationary_no_decay_preserves_nonuniform_density() {
    let cfg=Config{density_decay:0.,cooling:0.,..config()};
    let mut sim=Simulation::new(cfg.clone()).unwrap();let mut cells=vec![Cell::default();cfg.padded_len().unwrap()];
    for z in 0..cfg.cells[2] as usize {for y in 0..cfg.cells[1] as usize {for x in 0..cfg.cells[0] as usize {
        cells[at(x,y,z,&cfg)].s[0]=(x+2*y+3*z) as f32/64.;
    }}}
    sim.import_mac(&cells,&vec![[0.;4];cells.len()],Clock::default(),0).unwrap();
    let initial=field(&sim,Field::Density);sim.step_fixed(20).unwrap();
    assert_eq!(initial,field(&sim,Field::Density));
}
#[test]
fn source_changes_are_visible_and_reset_replays() {
    let cfg=Config{boundary:Boundary::Open,..config()};let mut sim=Simulation::new(cfg).unwrap();
    sim.set_emitter(0,Emitter{position:[0.3,0.1,0.3],radius:0.09,speed:0.4,..Emitter::default()}).unwrap();
    sim.step_fixed(24).unwrap();let density=field(&sim,Field::Density);assert!(density.iter().any(|v|*v>0.));
    sim.reset();sim.step_fixed(24).unwrap();assert_eq!(density,field(&sim,Field::Density));
    let max=sim.metrics().max_density;sim.remove_emitter(0).unwrap();sim.step_fixed(24).unwrap();
    assert!(sim.metrics().max_density<=max+1e-5);
}
#[test]
fn closed_walls_keep_normal_face_velocity_zero() {
    let cfg=config();let mut sim=Simulation::new(cfg.clone()).unwrap();
    sim.set_emitter(0,Emitter{position:[0.3,0.1,0.3],radius:0.09,speed:0.5,..Emitter::default()}).unwrap();
    sim.step_fixed(20).unwrap();
    let n=cfg.cells.map(|n|n as usize);let cells=sim.mac_cells();
    for z in 0..=n[2] {for y in 0..=n[1] {for x in 0..=n[0] {
        let pos=[x,y,z];for a in 0..3 {
            if (0..3).all(|j|pos[j]<n[j]+usize::from(a==j)) && (pos[a]==0||pos[a]==n[a]) {
                assert_eq!(cells[at(x,y,z,&cfg)].v[a],0.);
            }
        }
    }}}
}

/// Underresolved sidestream source used by the shipped low/medium presets.
/// Speed/heat disabled to isolate one step of density injection from transport.
#[test]
fn subgrid_emitter_does_not_disappear_at_cell_corners() {
    let r=0.007f32;let length=0.018f32;let rate=6.0f32;
    for (cells,dx) in [([10,16,10],0.024),([20,32,20],0.012),([40,64,40],0.006)] {
        let cfg=Config{cells,cell_size:dx,density_decay:0.,cooling:0.,buoyancy:0.,density_weight:0.,vorticity:0.,drag:0.,max_velocity:3.,pressure_iterations:1,..Config::default()};
        let expected=0.3*std::f64::consts::PI*(r as f64).powi(2)*(length as f64)*(rate as f64)*(cfg.fixed_dt as f64);
        for phase in [0.,0.25,0.5,0.75] {
            let mut s=Simulation::new(cfg.clone()).unwrap();
            s.set_emitter(0,Emitter{position:[0.12+phase*dx,0.06,0.12+phase*dx],direction:[0.,1.,0.],radius:r,length,speed:0.,density_rate:rate,temperature:0.,enabled:true}).unwrap();
            s.step_fixed(1).unwrap();let ratio=s.metrics().density_integral/expected;
            assert!((0.7..1.3).contains(&ratio),"dx={dx}, phase={phase}, ratio={ratio}");
        }
    }
}
