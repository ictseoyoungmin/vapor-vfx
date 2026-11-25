//! Native wgpu implementation. Web uses the same WGSL with an async JS host.
//! No WebGL fallback, native GPU pointer fabrication, or synchronous WASM waits.
use std::{borrow::Cow, collections::BTreeMap, sync::{Arc,atomic::{AtomicU8,Ordering},mpsc,Mutex},time::{Duration,Instant}};
use vapor_core::{Config,Error,Scene,Simulation};
use vapor_core::{runtime::Clock,solver::Cell};
use crate::{BackendOptions,ALLOW_SOFTWARE_GPU,protocol::*};
mod schedule { include!("passes.rs"); }
use schedule::*;

pub struct Gpu {
    pub scene:Scene,
    pub software:bool,
    pub allocated_bytes:u64,
    cfg:Config,options:BackendOptions,hybrid:bool,
    _instance:wgpu::Instance,device:wgpu::Device,queue:wgpu::Queue,
    failure:Arc<AtomicU8>, // 0 healthy, 1 device/API error, 2 numerical invalidity
    params:wgpu::Buffer,controls:wgpu::Buffer,state:[wgpu::Buffer;3],aux:wgpu::Buffer,
    counters:wgpu::Buffer,detail:Option<[wgpu::Buffer;3]>,atlas:wgpu::Buffer,
    active:usize,detail_active:usize,
    // One reusable staging buffer; independent from the process-wide FFI registry.
    readback:Mutex<wgpu::Buffer>,
    // Separate staging slot: diagnostic/synchronous snapshots cannot invalidate it.
    async_atlas:wgpu::Buffer,
    async_map:Option<(Arc<AtomicU8>,Instant)>,
    main_pipelines:BTreeMap<String,wgpu::ComputePipeline>,detail_pipelines:BTreeMap<String,wgpu::ComputePipeline>,
    pack_main:wgpu::ComputePipeline,pack_detail:wgpu::ComputePipeline,
    main_groups:Vec<Vec<wgpu::BindGroup>>,detail_groups:Vec<Vec<Vec<wgpu::BindGroup>>>,pack_groups:Vec<Vec<wgpu::BindGroup>>,
}
fn layout(device:&wgpu::Device,label:&str,kinds:&[u8])->wgpu::BindGroupLayout {
    let entries:Vec<_>=kinds.iter().enumerate().map(|(binding,&kind)|wgpu::BindGroupLayoutEntry{
        binding:binding as u32,visibility:wgpu::ShaderStages::COMPUTE,
        ty:wgpu::BindingType::Buffer{ty:if kind==0{wgpu::BufferBindingType::Uniform}else{wgpu::BufferBindingType::Storage{read_only:kind==1}},has_dynamic_offset:false,min_binding_size:None},count:None,
    }).collect();
    device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor{label:Some(label),entries:&entries})
}
fn bind(device:&wgpu::Device,layout:&wgpu::BindGroupLayout,buffers:&[&wgpu::Buffer])->wgpu::BindGroup{
    let entries:Vec<_>=buffers.iter().enumerate().map(|(i,b)|wgpu::BindGroupEntry{binding:i as u32,resource:b.as_entire_binding()}).collect();
    device.create_bind_group(&wgpu::BindGroupDescriptor{label:Some("vapor-buffer-bindings"),layout,entries:&entries})
}
fn pipeline(device:&wgpu::Device,layout:&wgpu::BindGroupLayout,module:&wgpu::ShaderModule,entry:&str)->wgpu::ComputePipeline{
    let pl=device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor{label:Some(entry),bind_group_layouts:&[layout],push_constant_ranges:&[]});
    device.create_compute_pipeline(&wgpu::ComputePipelineDescriptor{label:Some(entry),layout:Some(&pl),module,entry_point:Some(entry),compilation_options:Default::default(),cache:None})
}
fn dispatch(encoder:&mut wgpu::CommandEncoder,pipeline:&wgpu::ComputePipeline,group:&wgpu::BindGroup,count:u32){
    let mut pass=encoder.begin_compute_pass(&wgpu::ComputePassDescriptor{label:Some("vapor-dispatch"),timestamp_writes:None});
    pass.set_pipeline(pipeline);pass.set_bind_group(0,group,&[]);pass.dispatch_workgroups(count.div_ceil(WORKGROUP),1,1);
}
impl Gpu {
    pub fn new(cfg:Config,options:BackendOptions,hybrid:bool)->Result<Self,Error>{
        options.validate(&cfg)?;
        pollster::block_on(Self::create(cfg,options,hybrid))
    }
    async fn create(cfg:Config,options:BackendOptions,hybrid:bool)->Result<Self,Error>{
        let instance=wgpu::Instance::new(&wgpu::InstanceDescriptor{backends:wgpu::Backends::PRIMARY,..Default::default()});
        let adapter=instance.request_adapter(&wgpu::RequestAdapterOptions{power_preference:wgpu::PowerPreference::HighPerformance,force_fallback_adapter:false,compatible_surface:None}).await.map_err(|_|Error::BackendUnavailable)?;
        let info=adapter.get_info();
        let diagnostics=std::env::var_os("VAPOR_GPU_DIAGNOSTICS").is_some();
        if diagnostics {eprintln!("VAPOR_ADAPTER name={:?} vendor={} device={} type={:?} backend={:?} driver={:?} driver_info={:?}",
            info.name,info.vendor,info.device,info.device_type,info.backend,info.driver,info.driver_info);}
        let software=info.device_type==wgpu::DeviceType::Cpu;
        if software && options.flags&ALLOW_SOFTWARE_GPU==0{return Err(Error::BackendUnavailable);}
        let (device,queue)=adapter.request_device(&wgpu::DeviceDescriptor{label:Some("Vapor compute device"),..Default::default()}).await.map_err(|_|Error::BackendUnavailable)?;
        let failure=Arc::new(AtomicU8::new(0));
        let errors=Arc::clone(&failure);device.on_uncaptured_error(Arc::new(move |error:wgpu::Error|{if diagnostics {eprintln!("VAPOR_GPU_ERROR: {error}");}errors.store(1,Ordering::Release);}));
        let lost=Arc::clone(&failure);device.set_device_lost_callback(move |_,_|{lost.store(1,Ordering::Release);});
        let n=cfg.padded_len()? as u64;let fine=cfg.voxel_count() as u64*(options.detail_scale as u64).pow(3);
        let limits=device.limits();
        if [n*32,n*16,fine*16,fine*4].iter().any(|&s|s>limits.max_buffer_size||s>limits.max_storage_buffer_binding_size as u64)||
           n.div_ceil(WORKGROUP as u64)>limits.max_compute_workgroups_per_dimension as u64||fine.div_ceil(WORKGROUP as u64)>limits.max_compute_workgroups_per_dimension as u64 {
            return Err(Error::Capacity);
        }
        device.push_error_scope(wgpu::ErrorFilter::Validation);
        let buffer=|label:&str,size:u64,usage:wgpu::BufferUsages|device.create_buffer(&wgpu::BufferDescriptor{label:Some(label),size,mapped_at_creation:false,usage});
        let usage=wgpu::BufferUsages::STORAGE|wgpu::BufferUsages::COPY_SRC|wgpu::BufferUsages::COPY_DST;
        let params=buffer("vapor-params",128,wgpu::BufferUsages::UNIFORM|wgpu::BufferUsages::COPY_DST);
        let controls=buffer("vapor-controls",CONTROL_BYTES as u64,usage);
        let state=std::array::from_fn(|_|buffer("vapor-MAC",n*32,usage));
        let aux=buffer("vapor-curl-divergence",n*16,usage);let counters=buffer("vapor-counters",8,usage);
        let detail:Option<[wgpu::Buffer;3]>=if hybrid||options.detail_scale>1 {Some(std::array::from_fn(|_|buffer("vapor-detail",fine*16,usage)))}else{None};
        let dummy=buffer("vapor-unused-detail",16,usage);let atlas=buffer("vapor-RGBA8-atlas",fine*4,usage);
        let readback_bytes=(n*48+8).max(fine*4+8);
        let readback=Mutex::new(buffer("vapor-reusable-readback",readback_bytes,
            wgpu::BufferUsages::MAP_READ|wgpu::BufferUsages::COPY_DST));
        let async_atlas=buffer("vapor-async-atlas",fine*4+8,wgpu::BufferUsages::MAP_READ|wgpu::BufferUsages::COPY_DST);
        let ml=layout(&device,"vapor-MAC-layout",&[0,1,1,2,1,2,2]);
        let dl=layout(&device,"vapor-detail-layout",&[0,1,1,1,2,1,2]);
        let el=layout(&device,"vapor-export-layout",&[0,1,1,2]);
        let module=|label:&str,text:&str|device.create_shader_module(wgpu::ShaderModuleDescriptor{label:Some(label),source:wgpu::ShaderSource::Wgsl(Cow::Borrowed(text))});
        let main_module=module("vapor-MAC-WGSL",MAIN_SHADER);let detail_module=module("vapor-detail-WGSL",DETAIL_SHADER);let export_module=module("vapor-export-WGSL",EXPORT_SHADER);
        let mut main_pipelines=BTreeMap::new();
        for &(entry,_) in BEFORE.iter().chain(PRESSURE).chain(AFTER){
            if !main_pipelines.contains_key(entry){main_pipelines.insert(entry.to_string(),pipeline(&device,&ml,&main_module,entry));}
        }
        let mut detail_pipelines=BTreeMap::new();for &(entry,_) in DETAIL{detail_pipelines.insert(entry.to_string(),pipeline(&device,&dl,&detail_module,entry));}
        let pack_main=pipeline(&device,&el,&export_module,"pack_main");let pack_detail=pipeline(&device,&el,&export_module,"pack_detail");
        let mut main_groups=Vec::new();
        for a in 0..2 {let b=1-a;
            main_groups.push(vec![
                bind(&device,&ml,&[&params,&controls,&state[a],&state[b],&state[2],&aux,&counters]),
                bind(&device,&ml,&[&params,&controls,&state[a],&state[2],&state[a],&aux,&counters]),
                bind(&device,&ml,&[&params,&controls,&state[b],&state[a],&state[2],&aux,&counters]),
            ]);
        }
        let mut detail_groups=Vec::new();let mut pack_groups=Vec::new();
        for coarse in 0..2 {let mut groups=Vec::new();let mut exports=Vec::new();
            for a in 0..2 {
                if let Some(d)=&detail {
                    groups.push(vec![
                        bind(&device,&dl,&[&params,&controls,&state[coarse],&d[a],&d[1-a],&d[2],&counters]),
                        bind(&device,&dl,&[&params,&controls,&state[coarse],&d[a],&d[2],&d[a],&counters]),
                    ]);
                    exports.push(bind(&device,&el,&[&params,&state[coarse],&d[a],&atlas]));
                }else{exports.push(bind(&device,&el,&[&params,&state[coarse],&dummy,&atlas]));}
            }detail_groups.push(groups);pack_groups.push(exports);
        }
        if let Some(error)=device.pop_error_scope().await {
            if diagnostics {eprintln!("VAPOR_GPU_VALIDATION: {error}");}
            return Err(Error::GpuFailure);
        }
        if failure.load(Ordering::Acquire)!=0{return Err(Error::GpuFailure);}
        queue.write_buffer(&params,0,&parameters(&cfg,options.detail_scale));
        let allocated_bytes=readback_bytes+fine*4+8+128+CONTROL_BYTES as u64+n*112+8+fine*4+16+if detail.is_some(){fine*48}else{0};
        Ok(Self{scene:Scene::default(),software,allocated_bytes,cfg,options,hybrid,_instance:instance,device,queue,failure,
            params,controls,state,aux,counters,detail,atlas,readback,async_atlas,async_map:None,active:0,detail_active:0,main_pipelines,detail_pipelines,pack_main,pack_detail,main_groups,detail_groups,pack_groups})
    }
    pub fn check(&self)->Result<(),Error>{
        self.device.poll(wgpu::PollType::Poll).map_err(|_|Error::GpuFailure)?;
        match self.failure.load(Ordering::Acquire){0=>Ok(()),2=>Err(Error::NonFiniteState),_=>Err(Error::GpuFailure)}
    }
    pub fn reset(&mut self)->Result<(),Error>{
        if self.failure.load(Ordering::Acquire)==1{return Err(Error::GpuFailure);}
        let mut enc=self.device.create_command_encoder(&wgpu::CommandEncoderDescriptor{label:Some("vapor-reset")});
        for b in &self.state{enc.clear_buffer(b,0,None);}enc.clear_buffer(&self.aux,0,None);enc.clear_buffer(&self.counters,0,None);enc.clear_buffer(&self.atlas,0,None);
        if let Some(d)=&self.detail{for b in d{enc.clear_buffer(b,0,None);}}
        self.queue.submit(Some(enc.finish()));self.active=0;self.detail_active=0;
        // Do not overwrite a concurrent device-lost event with a successful reset.
        let _=self.failure.compare_exchange(2,0,Ordering::AcqRel,Ordering::Acquire);self.check()
    }
    fn main_pass(&mut self,enc:&mut wgpu::CommandEncoder,entry:&str,kind:&str){
        let slot=match kind{"predict"=>1,"inplace"=>2,_=>0};
        dispatch(enc,&self.main_pipelines[entry],&self.main_groups[self.active][slot],self.cfg.padded_len().unwrap() as u32);
        if kind=="swap"{self.active=1-self.active;}
    }
    pub fn step(&mut self,time:f64,cpu_cells:Option<&[Cell]>)->Result<(),Error>{
        self.check()?;
        if self.hybrid!=cpu_cells.is_some(){return Err(Error::InvalidArgument("hybrid upload contract mismatch"));}
        let packet=controls(&self.cfg,&self.scene,time)?;
        let mut params=parameters(&self.cfg,self.options.detail_scale);
        for(offset,value)in [(84,self.options.detail_turbulence),(88,(time%16.) as f32),(92,self.options.detail_frequency)]{params[offset..offset+4].copy_from_slice(&value.to_le_bytes());}
        self.queue.write_buffer(&self.params,0,&params);self.queue.write_buffer(&self.controls,0,&packet);
        if let Some(cells)=cpu_cells {
            if cells.len()!=self.cfg.padded_len()?{return Err(Error::InvalidArgument("hybrid MAC length mismatch"));}
            self.queue.write_buffer(&self.state[0],0,&encode_cells(cells));self.active=0;
        }
        let mut enc=self.device.create_command_encoder(&wgpu::CommandEncoderDescriptor{label:Some("vapor-step")});
        if !self.hybrid {
            for &(entry,kind) in BEFORE{self.main_pass(&mut enc,entry,kind);}
            for _ in 0..self.cfg.pressure_iterations{for &(entry,kind)in PRESSURE{self.main_pass(&mut enc,entry,kind);}}
            for &(entry,kind)in AFTER{self.main_pass(&mut enc,entry,kind);}
        }
        if self.detail.is_some(){
            let count=self.cfg.voxel_count() as u32*self.options.detail_scale.pow(3);
            for &(entry,kind)in DETAIL{
                let slot=usize::from(kind=="predict");
                dispatch(&mut enc,&self.detail_pipelines[entry],&self.detail_groups[self.active][self.detail_active][slot],count);
                if kind=="swap"{self.detail_active=1-self.detail_active;}
            }
        }
        self.queue.submit(Some(enc.finish()));self.check()
    }
    // A single map for all requested regions. Waiting is bounded and used only for
    // explicit snapshots, never for the one-way CPU->GPU simulation update.
    fn read_regions(&self,regions:&[(&wgpu::Buffer,u64)])->Result<Vec<u8>,Error>{
        self.check()?;
        let bytes: u64=regions.iter().map(|(_,n)|*n).sum();
        let staging=self.readback.lock().map_err(|_|Error::Internal)?;
        if bytes==0 || bytes>staging.size() || bytes%4!=0 {
            return Err(Error::InvalidArgument("invalid readback byte range"));
        }
        let result=(|| {
            let mut enc=self.device.create_command_encoder(&wgpu::CommandEncoderDescriptor {
                label:Some("vapor-readback-copy")
            });
            let mut offset=0;
            for &(buffer,size) in regions {
                enc.copy_buffer_to_buffer(buffer,0,&*staging,offset,size);
                offset+=size;
            }
            let submission=self.queue.submit(Some(enc.finish()));
            let slice=staging.slice(0..bytes);
            let (tx,rx)=mpsc::channel();
            slice.map_async(wgpu::MapMode::Read,move|result|{let _=tx.send(result);});
            self.device.poll(wgpu::PollType::Wait {
                submission_index:Some(submission),timeout:Some(Duration::from_secs(30))
            }).map_err(|_|Error::GpuFailure)?;
            rx.recv_timeout(Duration::from_secs(1)).map_err(|_|Error::GpuFailure)?
                .map_err(|_|Error::GpuFailure)?;
            let output=slice.get_mapped_range().to_vec();
            self.check()?;
            Ok(output)
        })();
        // Also cancels any still-pending map after a timeout. Never leave the buffer mapped.
        staging.unmap();
        if result.is_err() {
            let _=self.failure.compare_exchange(0,1,Ordering::AcqRel,Ordering::Acquire);
        }
        result
    }
    fn validate_counters(&self,bytes:&[u8])->Result<u64,Error>{
        if bytes.len()!=8{return Err(Error::Internal);}
        if u32::from_le_bytes(bytes[..4].try_into().unwrap())!=0{
            let _=self.failure.compare_exchange(0,2,Ordering::AcqRel,Ordering::Acquire);return Err(Error::NonFiniteState);
        }Ok(u32::from_le_bytes(bytes[4..].try_into().unwrap()) as u64)
    }
    pub fn copy_atlas(&self,out:&mut[u8])->Result<(),Error>{
        let size=self.atlas.size() as usize;if out.len()<size{return Err(Error::BufferTooSmall);}self.check()?;
        let mut enc=self.device.create_command_encoder(&wgpu::CommandEncoderDescriptor{label:Some("vapor-pack-atlas")});
        dispatch(&mut enc,if self.detail.is_some(){&self.pack_detail}else{&self.pack_main},&self.pack_groups[self.active][self.detail_active],(size/4) as u32);
        self.queue.submit(Some(enc.finish()));let bytes=self.read_regions(&[(&self.atlas,size as u64),(&self.counters,8)])?;
        self.validate_counters(&bytes[size..])?;out[..size].copy_from_slice(&bytes[..size]);Ok(())
    }
    // Capture pack and copy in one submission, so subsequent steps cannot change this snapshot.
    // Callback only writes a request-local atomic, never locks the engine or calls a foreign pointer.
    pub fn begin_atlas(&mut self)->Result<(),Error>{
        self.check()?;
        if self.async_map.is_some(){return Err(Error::Internal);}
        let size=self.atlas.size();
        let mut enc=self.device.create_command_encoder(&wgpu::CommandEncoderDescriptor{label:Some("vapor-async-atlas-copy")});
        dispatch(&mut enc,if self.detail.is_some(){&self.pack_detail}else{&self.pack_main},
            &self.pack_groups[self.active][self.detail_active],(size/4) as u32);
        enc.copy_buffer_to_buffer(&self.atlas,0,&self.async_atlas,0,size);
        enc.copy_buffer_to_buffer(&self.counters,0,&self.async_atlas,size,8);
        self.queue.submit(Some(enc.finish()));
        let state=Arc::new(AtomicU8::new(0));
        let callback=Arc::clone(&state);
        self.async_map=Some((state,Instant::now()));
        self.async_atlas.slice(..).map_async(wgpu::MapMode::Read,move |result|{
            callback.store(if result.is_ok(){1}else{2},Ordering::Release);
        });
        Ok(())
    }
    pub fn cancel_atlas(&mut self){
        if self.async_map.take().is_some(){self.async_atlas.unmap();}
    }
    pub fn poll_atlas(&mut self,out:&mut[u8])->Result<bool,Error>{
        let size=self.atlas.size() as usize;
        if out.len()<size{return Err(Error::BufferTooSmall);}
        if let Err(e)=self.check(){self.cancel_atlas();return Err(e);}
        let (state,started)=self.async_map.as_ref().ok_or(Error::InvalidHandle)?;
        match state.load(Ordering::Acquire){
            0 if started.elapsed()<Duration::from_secs(30)=>return Ok(false),
            1=>{},
            _=>{
                self.cancel_atlas();
                let _=self.failure.compare_exchange(0,1,Ordering::AcqRel,Ordering::Acquire);
                return Err(Error::GpuFailure);
            }
        }
        let result={
            let view=self.async_atlas.slice(..).get_mapped_range();
            self.validate_counters(&view[size..]).map(|_|{out[..size].copy_from_slice(&view[..size]);true})
        }; // view must be dropped BEFORE unmap
        self.cancel_atlas();
        result
    }
    pub fn snapshot(&self,clock:Clock)->Result<Simulation,Error>{
        let n=self.cfg.padded_len()?;let bytes=self.read_regions(&[(&self.state[self.active],(n*32) as u64),(&self.aux,(n*16) as u64),(&self.counters,8)])?;
        let clamps=self.validate_counters(&bytes[n*48..])?;let cells=decode_cells(&bytes[..n*32])?;
        let rhs:Vec<[f32;4]>=bytes[n*32..n*48].chunks_exact(16).map(|c|std::array::from_fn(|i|f32::from_le_bytes(c[i*4..i*4+4].try_into().unwrap()))).collect();
        let mut result=Simulation::new(self.cfg.clone())?;result.import_mac(&cells,&rhs,clock,clamps)?;Ok(result)
    }
}
impl Drop for Gpu {fn drop(&mut self){self.cancel_atlas();}}
#[cfg(test)] mod tests{
    use super::*;
    #[test]fn wgsl_parse_and_validate(){
        for (name,source)in [("MAC",MAIN_SHADER),("detail",DETAIL_SHADER),("export",EXPORT_SHADER),("direct volume",include_str!("../../../shaders/render/volume.wgsl")),("temporal volume",include_str!("../../../shaders/render/temporal.wgsl")),("fidelity volume",concat!(include_str!("../../../shaders/render/volume.wgsl"),"\n",include_str!("../../../shaders/render/fidelity.wgsl")))]{
            let module=naga::front::wgsl::parse_str(source).unwrap_or_else(|e|panic!("{name}: {}",e.emit_to_string(source)));
            naga::valid::Validator::new(naga::valid::ValidationFlags::all(),naga::valid::Capabilities::empty()).validate(&module).unwrap_or_else(|e|panic!("{name}: {e:?}"));
        }
    }
}
