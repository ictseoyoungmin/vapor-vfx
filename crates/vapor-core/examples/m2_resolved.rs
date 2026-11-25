//! Real Rust local resolved source A/B; no Lab or renderer fallback.
use std::{fs,io::Write,path::Path,time::Instant};
use vapor_core::{Simulation,Field,EmissionProfile,ResolvedPlumeOptions};
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
    let id:u32=args.get(2).ok_or("effect id 1 or 2 required")?.parse()?;
    if ![1,2].contains(&id){return Err("effect id must be 1 or 2".into());}
    let mode=args.get(3).ok_or("mode legacy_source/matched/seeded required")?.as_str();
    if !["legacy_source","matched","seeded"].contains(&mode){return Err("invalid mode".into());}
    let seconds:f64=args.get(4).map(|s|s.parse()).transpose()?.unwrap_or(4.);
    if !seconds.is_finite()||!(0.25..=4.).contains(&seconds){return Err("seconds 0.25..4 required".into());}
    let mut metrics=fs::File::create(out.join("metrics.csv"))?;
    writeln!(metrics,"effect,mode,tick,seconds,density_integral,divergence_rms,pressure_residual_rms,clamps,step_ms,injected,outflow,decayed,saturated,budget_residual,substeps,cg_iterations,cg_initial_rms,cg_residual_rms")?;
    {
        let mut p=preset(id,1)?.preset;let mut cfg=p.config.clone();
        if id==1{cfg.cells=[36,72,36];cfg.cell_size=0.003;p.emitter.position=[0.054,0.03,0.054];}
        else{cfg.cells=[64,32,32];cfg.cell_size=0.01;p.emitter.position=[0.10,0.16,0.16];}
        cfg.fixed_dt=1./120.;cfg.pressure_iterations=256;cfg.validate()?;
        let extent=cfg.extent().map(|v|v as f64);let ticks=(seconds*120.).round() as u32;
        let sample_ticks=[(ticks as f64*0.125).round().max(1.) as u32,(ticks as f64*0.375).round().max(1.) as u32,(ticks as f64*0.625).round().max(1.) as u32,ticks];
        let (width,height,eye,target,fov)=if id==1{(260,340,[0.054,0.108,-0.34],[0.054,0.108,0.054],34.)}else{(340,250,[0.32,0.16,-0.80],[0.32,0.16,0.16],34.)};
        let camera=FidelityCamera{width,height,eye,target,fov,steps:160,exposure:1.,jitter:0.5,dark:true};
        let m=p.material;let material=OpticalMaterial{colour:m.colour.map(|v|v as f64),extinction:m.extinction as f64,anisotropy:m.anisotropy as f64,albedo:m.albedo as f64,emission:m.emission as f64,thermal_fade:m.thermal_fade as f64,ambient:m.ambient as f64};
        let lighting=FidelityLighting{direction:[-0.80,0.56,0.16],radiance:[2.6,2.45,2.2],sky:[0.05,0.07,0.10],ground:[0.02,0.02,0.02],multi_scatter:0.20,shadow_steps:20,light_scale:0.5};
        {
            let mut sim=if mode=="legacy_source"{Simulation::new_converged_density(cfg.clone())?}else{Simulation::new_resolved_plume(cfg.clone(),ResolvedPlumeOptions{seed_amplitude:if mode=="seeded"{0.05}else{0.},seed_frequency_hz:0.2*p.emitter.speed/(2.*p.emitter.radius)})?};
            sim.set_emitter(0,p.emitter.clone())?;
            if !p.profile.is_empty(){let curve=|i:usize|Curve::new(p.profile.iter().map(|r|Point{x:r[0],y:r[i]}).collect());sim.set_profile(0,Some(EmissionProfile{curve:BreathProfile::new(p.duration,curve(1)?,curve(2)?,curve(3)?)?,repeat:false,start_time:0.}))?;}
            for tick in 1..=ticks {
                let t=Instant::now();sim.step_fixed(1)?;let ms=t.elapsed().as_secs_f64()*1000.;let m=sim.metrics();
                if m.non_finite!=0{return Err("nonfinite state".into());}
                write!(metrics,"{},{},{},{},{},{},{},{},{}",p.key,mode,tick,m.time,m.density_integral,m.divergence_rms,m.pressure_residual_rms,m.clamped_velocities,ms)?;
                if let Some(b)=sim.density_budget(){if b.residual.abs()>1e-10+1e-6*(b.before+b.injected){return Err("density budget closure failed".into());}let q=sim.pressure_report().ok_or("missing pressure report")?;writeln!(metrics,",{},{},{},{},{},{},{},{},{}",b.injected,b.boundary_outflow,b.decayed,b.saturated,b.residual,b.substeps,q.iterations,q.initial_divergence_rms,q.final_residual_rms)?;}else{return Err("missing density budget".into());}
                if sample_ticks.contains(&tick) {
                    let mut density=vec![0.;cfg.voxel_count()];let mut temperature=density.clone();sim.copy_field(Field::Density,&mut density)?;sim.copy_field(Field::Temperature,&mut temperature)?;
                    let stem=format!("{}-{mode}-{tick:04}",p.key);
                    for (name,field) in [("density",&density),("temperature",&temperature)]{let mut f=fs::File::create(out.join(format!("{stem}.{name}.f32")))?;for q in field{f.write_all(&q.to_le_bytes())?;}}
                    if tick==ticks&&!density.iter().any(|&v|v>0.){return Err("empty plume".into());}
                    let img=FidelityRenderer::prepare(FidelityGrid{cells:cfg.cells,extent,density_cap:cfg.density_cap as f64},FidelityFields{density,temperature},material,lighting)?.render(camera,None)?;
                    write_ppm(&out.join(format!("{stem}.ppm")),width,height,&img.rgba)?;
                    if tick==ticks&&!img.alpha.iter().any(|&v|v>0.){return Err("invisible plume".into());}
                }
            }
        }
    }
    println!("PASS actual Rust local resolved plume — execution only, no visual acceptance");Ok(())
}
