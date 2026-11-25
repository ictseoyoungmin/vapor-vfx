use vapor_core::{Config,Emitter,Simulation};
fn main()->Result<(),Box<dyn std::error::Error>>{
 let mut sim=Simulation::new(Config{cells:[16,20,16],cell_size:0.04,..Config::default()})?;
 sim.set_emitter(0,Emitter{position:[0.32,0.12,0.32],..Emitter::default()})?;
 let start=std::time::Instant::now();sim.step_fixed(60)?;
 println!("profile=game-mac-v1 metrics={:?} elapsed={:?}",sim.metrics(),start.elapsed());Ok(())
}
