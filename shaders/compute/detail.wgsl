// One-way high-resolution passive density/temperature. Coarse MAC velocity remains
// authoritative. No fine-to-coarse pressure/buoyancy feedback is implied.
struct Params {
    grid:vec4<u32>,origin_dx:vec4<f32>,step:vec4<f32>,physics:vec4<f32>,
    wind_cap:vec4<f32>,relaxation:vec4<f32>,counts:vec4<u32>,detail:vec4<u32>,
}
struct Cell {velocity:vec4<f32>,scalar:vec4<f32>}
struct Emitter {position_radius:vec4<f32>,direction_length:vec4<f32>,rates:vec4<f32>}
struct Obstacle {a_radius:vec4<f32>,b_kind:vec4<f32>,velocity_enabled:vec4<f32>}
struct Controls {emitters:array<Emitter,32>,obstacles:array<Obstacle,32>}
struct Counters {invalid:atomic<u32>,clamps:atomic<u32>}
@group(0) @binding(0) var<uniform> cfg:Params;
@group(0) @binding(1) var<storage,read> controls:Controls;
@group(0) @binding(2) var<storage,read> coarse:array<Cell>;
@group(0) @binding(3) var<storage,read> source:array<vec4<f32>>;
@group(0) @binding(4) var<storage,read_write> output_cells:array<vec4<f32>>;
@group(0) @binding(5) var<storage,read> prediction:array<vec4<f32>>;
@group(0) @binding(6) var<storage,read_write> counters:Counters;
fn count()->u32{return cfg.detail.y*cfg.detail.z*cfg.detail.w;}
fn coord(i:u32)->vec3<u32>{return vec3<u32>(i%cfg.detail.y,(i/cfg.detail.y)%cfg.detail.z,i/(cfg.detail.y*cfg.detail.z));}
fn index(c:vec3<u32>)->u32{return c.x+cfg.detail.y*(c.y+cfg.detail.z*c.z);}
fn coarse_index(c:vec3<u32>)->u32{return c.x+(cfg.grid.x+1u)*(c.y+(cfg.grid.y+1u)*c.z);}
fn dx()->f32{return cfg.origin_dx.w/f32(cfg.detail.x);}
fn world(p:vec3<f32>)->vec3<f32>{return cfg.origin_dx.xyz+p*dx();}
fn sdf(o:Obstacle,p:vec3<f32>)->f32{
    if(o.velocity_enabled.w<0.5){return 1e30;}
    if(o.b_kind.w<0.5){let ba=o.b_kind.xyz-o.a_radius.xyz;let pa=p-o.a_radius.xyz;return length(pa-ba*clamp(dot(pa,ba)/max(dot(ba,ba),1e-12),0.0,1.0))-o.a_radius.w;}
    let q=abs(p-(o.a_radius.xyz+o.b_kind.xyz)*0.5)-(o.b_kind.xyz-o.a_radius.xyz)*0.5;
    return length(max(q,vec3<f32>(0.0)))+min(max(q.x,max(q.y,q.z)),0.0);
}
fn solid_world(p:vec3<f32>)->bool{for(var i=0u;i<32u;i++){if(sdf(controls.obstacles[i],p)<0.0){return true;}}return false;}
fn coarse_component(p:vec3<f32>,a:u32)->f32{
    var upper=cfg.grid.xyz-vec3<u32>(1u);upper[a]+=1u;var offset=vec3<f32>(0.5);offset[a]=0.0;
    let q=clamp(p-offset,vec3<f32>(0.0),vec3<f32>(upper));let b=vec3<u32>(floor(q));let f=q-vec3<f32>(b);var result=0.0;
    for(var z=0u;z<2u;z++){for(var y=0u;y<2u;y++){for(var x=0u;x<2u;x++){
        let d=vec3<u32>(x,y,z);let w=select(vec3<f32>(1.0)-f,f,d!=vec3<u32>(0u));result+=w.x*w.y*w.z*coarse[coarse_index(min(b+d,upper))].velocity[a];
    }}}return result;
}
// Curl of a domain-tapered vector potential. The taper is INSIDE curl,
// including its gradient, so this kinematic contribution is divergence-free
// in continuous space. It is not a second pressure solve. Local coordinates
// make the field invariant to translating the entire simulation.
fn detail_ramp(x:f32)->vec2<f32>{
    let t=clamp(x,0.0,1.0);return vec2<f32>(t*t*(3.0-2.0*t),6.0*t*(1.0-t));
}
fn detail_wave(q:vec3<f32>,extent:vec3<f32>,k:f32,axis:vec3<f32>,pol:vec3<f32>,phase:f32)->vec3<f32>{
    let tau=6.283185307179586;
    // Reject wavelengths below 2 fine cells; smoothly restore by 4 cells.
    let resolved=detail_ramp((tau/(k*dx())-2.0)*0.5).x;
    if(resolved<=0.0){return vec3<f32>(0.0);}
    let width=max(4.0*dx(),3.0/k);
    let lx=detail_ramp(q.x/width);let rx=detail_ramp((extent.x-q.x)/width);
    let ly=detail_ramp(q.y/width);let ry=detail_ramp((extent.y-q.y)/width);
    let lz=detail_ramp(q.z/width);let rz=detail_ramp((extent.z-q.z)/width);
    let m=vec3<f32>(lx.x*rx.x,ly.x*ry.x,lz.x*rz.x);
    let dm=vec3<f32>(lx.y*rx.x-lx.x*rx.y,ly.y*ry.x-ly.x*ry.y,lz.y*rz.x-lz.x*rz.y)/width;
    let mask=m.x*m.y*m.z;
    let grad=vec3<f32>(dm.x*m.y*m.z,m.x*dm.y*m.z,m.x*m.y*dm.z);
    let angle=k*dot(axis,q)+phase;
    return resolved*cross(mask*cos(angle)*axis+sin(angle)*grad/k,pol);
}
fn detail_curl(p:vec3<f32>)->vec3<f32>{
    if(cfg.relaxation.y==0.0){return vec3<f32>(0.0);}
    let q=p*dx();let extent=vec3<f32>(cfg.detail.yzw)*dx();
    if(any(q<=vec3<f32>(0.0))||any(q>=extent)){return vec3<f32>(0.0);}
    let k=cfg.relaxation.w;let tau=6.283185307179586;
    // Binary-exact frequencies (21/16 and -34/16 Hz); a 16-second host
    // phase wrap is continuous. Neither band depends on emitter enable state.
    let a=detail_wave(q,extent,k,vec3<f32>(1.0,2.0,2.0)/3.0,vec3<f32>(0.0,0.7071067812,-0.7071067812),tau*fract(cfg.relaxation.z*1.3125)+0.73);
    let b=detail_wave(q,extent,2.3*k,vec3<f32>(2.0,-2.0,1.0)/3.0,vec3<f32>(0.7071067812,0.7071067812,0.0),tau*fract(-cfg.relaxation.z*2.125)+2.17);
    // Each band |curl| <= 1 + sqrt(3)*1.5/3 < 2. The convex
    // combination preserves the existing conservative host CFL budget.
    return cfg.relaxation.y*(0.58*a+0.42*b);
}
fn velocity(p:vec3<f32>)->vec3<f32>{
    let cp=p/f32(cfg.detail.x);let v=vec3<f32>(coarse_component(cp,0u),coarse_component(cp,1u),coarse_component(cp,2u));
    return v+detail_curl(p);
}
fn trace(p:vec3<f32>,dt:f32)->vec3<f32>{
    let k=dt/dx();var mid=p-velocity(p)*(0.5*k);
    // Closed domains do not lose passive scalars through a numerical backtrace
    // crossing a wall. Open domains retain zero exterior sampling.
    if(cfg.counts.z==1u){mid=clamp(mid,vec3<f32>(0.0),vec3<f32>(cfg.detail.yzw));}
    var end=p-velocity(mid)*k;
    if(cfg.counts.z==1u){end=clamp(end,vec3<f32>(0.0),vec3<f32>(cfg.detail.yzw));}
    let diff=end-p;
    var obstacles=false;for(var o=0u;o<32u;o++){obstacles=obstacles||controls.obstacles[o].velocity_enabled.w>0.5;}if(!obstacles){return end;}
    let steps=u32(clamp(ceil(length(diff)*2.0),1.0,256.0));var last=p;
    for(var i=1u;i<=steps;i++){let q=p+diff*(f32(i)/f32(steps));if(solid_world(world(q))){return last;}last=q;}return end;
}
fn sample_detail(p:vec3<f32>,predicted:bool)->vec2<f32>{
    if(any(p<vec3<f32>(0.0))||any(p>vec3<f32>(cfg.detail.yzw))){return vec2<f32>(0.0);}
    let upper=cfg.detail.yzw-vec3<u32>(1u);let q=clamp(p-vec3<f32>(0.5),vec3<f32>(0.0),vec3<f32>(upper));let b=vec3<u32>(floor(q));let f=q-vec3<f32>(b);var result=vec2<f32>(0.0);
    for(var z=0u;z<2u;z++){for(var y=0u;y<2u;y++){for(var x=0u;x<2u;x++){
        let d=vec3<u32>(x,y,z);let w=select(vec3<f32>(1.0)-f,f,d!=vec3<u32>(0u));let i=index(min(b+d,upper));var value=source[i].xy;if(predicted){value=prediction[i].xy;}result+=w.x*w.y*w.z*value;
    }}}return result;
}
fn limits(p:vec3<f32>)->vec4<f32>{
    let upper=vec3<i32>(cfg.detail.yzw)-vec3<i32>(1);let b=vec3<i32>(floor(p-vec3<f32>(0.5)));var low=vec2<f32>(1e30);var high=vec2<f32>(-1e30);
    for(var z=0;z<2;z++){for(var y=0;y<2;y++){for(var x=0;x<2;x++){
        let c=vec3<u32>(clamp(b+vec3<i32>(x,y,z),vec3<i32>(0),upper));let v=source[index(c)].xy;low=min(low,v);high=max(high,v);
    }}}return vec4<f32>(low,high);
}
fn smooth01(x:f32)->f32{let t=clamp(x,0.0,1.0);return t*t*(3.0-2.0*t);}
fn physical_length(e:Emitter)->f32{return select(e.position_radius.w,e.direction_length.w,e.direction_length.w>0.0);}
fn density_scale(e:Emitter)->f32{
    let l=physical_length(e);let r=e.position_radius.w/max(e.position_radius.w,dx()*1.1);return r*r*(l/max(l,dx()));
}
fn weight(e:Emitter,p:vec3<f32>)->f32{
    if(e.rates.w<0.5){return 0.0;}let q=p-e.position_radius.xyz;let along=dot(q,e.direction_length.xyz);let extent=max(physical_length(e),dx());let radius=max(e.position_radius.w,dx()*1.1);
    if(along< -dx()*0.5||along>extent+dx()*0.5){return 0.0;}return (1.0-smooth01(length(q-e.direction_length.xyz*along)/radius))*smooth01((along+dx()*0.5)/dx())*smooth01((extent+dx()*0.5-along)/dx());
}
@compute @workgroup_size(64) fn detail_classify(@builtin(global_invocation_id) gid:vec3<u32>){
    let i=gid.x;if(i>=count()){return;}var v=source[i];let solid=solid_world(world(vec3<f32>(coord(i))+vec3<f32>(0.5)));v.z=select(0.0,1.0,solid);if(solid){v.x=0.0;v.y=0.0;}output_cells[i]=v;
}
@compute @workgroup_size(64) fn detail_predict(@builtin(global_invocation_id) gid:vec3<u32>){
    let i=gid.x;if(i>=count()){return;}
    // A solid voxel must also be empty in the predictor; otherwise reverse
    // MacCormack sampling can import phantom scalar from inside geometry.
    if(source[i].z>0.5){output_cells[i]=vec4<f32>(0.0,0.0,1.0,0.0);return;}
    let p=vec3<f32>(coord(i))+vec3<f32>(0.5);let q=sample_detail(trace(p,cfg.step.x),false);output_cells[i]=vec4<f32>(q,source[i].zw);
}
@compute @workgroup_size(64) fn detail_correct(@builtin(global_invocation_id) gid:vec3<u32>){
    let i=gid.x;if(i>=count()){return;}let p=vec3<f32>(coord(i))+vec3<f32>(0.5);if(source[i].z>0.5){output_cells[i]=vec4<f32>(0.0,0.0,1.0,0.0);return;}
    let back=trace(p,cfg.step.x);let forward=trace(p,-cfg.step.x);let bounds=limits(back);let predicted=prediction[i].xy;
    var rho=predicted+min(2.0/max(length(back-p),1.0),1.0)*(clamp(predicted+0.5*(source[i].xy-sample_detail(forward,true)),bounds.xy,bounds.zw)-predicted);
    if(any(back<vec3<f32>(0.0))||any(back>vec3<f32>(cfg.detail.yzw))){rho=vec2<f32>(0.0);}
    rho=max(rho,vec2<f32>(0.0))*exp(-vec2<f32>(cfg.step.y,cfg.step.z)*cfg.step.x);
    for(var e=0u;e<32u;e++){let emitter=controls.emitters[e];let w=weight(emitter,world(p));rho.x+=emitter.rates.y*w*density_scale(emitter)*cfg.step.x;rho.y+=max(emitter.rates.z-rho.y,0.0)*(1.0-exp(-20.0*w*cfg.step.x));}
    if(!all(abs(rho)<=vec2<f32>(3.402823e38))){atomicOr(&counters.invalid,1u);rho=vec2<f32>(0.0);}
    output_cells[i]=vec4<f32>(min(rho.x,cfg.wind_cap.w),rho.y,0.0,0.0);
}
