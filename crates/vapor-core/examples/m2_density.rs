//! Real Rust CPU A/B, including the Rust Fidelity renderer. No fallback.
use std::{fs,io::Write,path::Path,time::Instant};
use vapor_core::{Simulation,Field,EmissionProfile};
use vapor_core::breath::{Curve,Point,BreathProfile};
use vapor_core::effects::preset;
use vapor_core::fidelity::{FidelityGrid,FidelityFields,OpticalMaterial,FidelityLighting,FidelityCamera,FidelityRenderer};

fn write_ppm(path:&Path,width:u32,height:u32,rgba:&[u8])->std::io::Result<()> {
    let mut f=fs::File::create(path)?;write!(f,"P6\n{width} {height}\n255\n")?;
    let rgb:Vec<u8>=rgba.chunks_exact(4).flat_map(|p|p[..3].iter().copied()).collect();f.write_all(&rgb)
}
fn main()->Result<(),Box<dyn std::error::Error>>{
    let args:Vec<String>=std::env::args().collect();
    let out=Path::new(args.get(1).ok_or("output directory required")?);fs::create_dir_all(out)?;
    let quality:u32=args.get(2).map(|s|s.parse()).transpose()?.unwrap_or(1);
    let mut metrics=fs::File::create(out.join("metrics.csv"))?;
    writeln!(metrics,"effect,mode,tick,seconds,density_integral,divergence_rms,pressure_residual_rms,clamps,step_ms,injected,outflow,decayed,saturated,budget_residual,substeps")?;
    for id in [1,2] {
        let p=preset(id,quality)?.preset;let cfg=p.config.clone();let extent=cfg.extent().map(|v|v as f64);
        let (width,height,eye,target,fov)=if id==1{(240,300,[0.12,0.18,-0.48],[0.12,0.18,0.12],37.)}else{(300,240,[0.38,0.38,-0.95],[0.38,0.38,0.4],38.)};
        let camera=FidelityCamera{width,height,eye,target,fov,steps:128,exposure:1.,jitter:0.5,dark:true};
        let m=p.material;let material=OpticalMaterial{colour:m.colour.map(|v|v as f64),extinction:m.extinction as f64,anisotropy:m.anisotropy as f64,albedo:m.albedo as f64,emission:m.emission as f64,thermal_fade:m.thermal_fade as f64,ambient:m.ambient as f64};
        let lighting=FidelityLighting{direction:[-0.80,0.56,0.16],radiance:[2.6,2.45,2.2],sky:[0.05,0.07,0.10],ground:[0.02,0.02,0.02],multi_scatter:0.20,shadow_steps:20,light_scale:0.5};
        for mode in ["legacy","conservative"] {
            let mut sim=if mode=="legacy"{Simulation::new(cfg.clone())?}else{Simulation::new_conservative_density(cfg.clone())?};
            sim.set_emitter(0,p.emitter.clone())?;
            if !p.profile.is_empty(){let curve=|i:usize|Curve::new(p.profile.iter().map(|r|Point{x:r[0],y:r[i]}).collect());sim.set_profile(0,Some(EmissionProfile{curve:BreathProfile::new(p.duration,curve(1)?,curve(2)?,curve(3)?)?,repeat:false,start_time:0.}))?;}
            for tick in 1..=90 {
                let t=Instant::now();sim.step_fixed(1)?;let ms=t.elapsed().as_secs_f64()*1000.;let m=sim.metrics();
                if m.non_finite!=0{return Err("nonfinite state".into());}
                write!(metrics,"{},{},{},{},{},{},{},{},{}",p.key,mode,tick,m.time,m.density_integral,m.divergence_rms,m.pressure_residual_rms,m.clamped_velocities,ms)?;
                if let Some(b)=sim.density_budget(){if b.residual.abs()>1e-10+1e-6*(b.before+b.injected){return Err("density budget closure failed".into());}writeln!(metrics,",{},{},{},{},{},{}",b.injected,b.boundary_outflow,b.decayed,b.saturated,b.residual,b.substeps)?;}else{writeln!(metrics,",,,,,,")?;}
                if [30,60,90].contains(&tick) {
                    let mut density=vec![0.;cfg.voxel_count()];let mut temperature=density.clone();sim.copy_field(Field::Density,&mut density)?;sim.copy_field(Field::Temperature,&mut temperature)?;
                    let stem=format!("{}-{mode}-{tick:04}",p.key);
                    for (name,field) in [("density",&density),("temperature",&temperature)]{let mut f=fs::File::create(out.join(format!("{stem}.{name}.f32")))?;for q in field{f.write_all(&q.to_le_bytes())?;}}
                    if tick==90&&!density.iter().any(|&v|v>0.){return Err("empty plume".into());}
                    let img=FidelityRenderer::prepare(FidelityGrid{cells:cfg.cells,extent,density_cap:cfg.density_cap as f64},FidelityFields{density,temperature},material,lighting)?.render(camera,None)?;
                    write_ppm(&out.join(format!("{stem}.ppm")),width,height,&img.rgba)?;
                    if tick==90&&!img.alpha.iter().any(|&v|v>0.){return Err("invisible plume".into());}
                }
            }
        }
    }
    println!("PASS actual Rust CPU A/B — comparison, not a visual acceptance decision");Ok(())
}
