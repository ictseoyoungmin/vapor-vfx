// game-mac-v1 GPU port. MAC storage: lower faces + one padded layer, x-fastest.
// Stencil passes are ping-pong. SOR alone updates in place, one parity/dispatch:
// same-parity cells never read another same-parity pressure. Separate dispatches
// provide the global red/black ordering; workgroupBarrier is NOT used as a grid barrier.
struct Params {
    grid: vec4<u32>, origin_dx: vec4<f32>, step: vec4<f32>, physics: vec4<f32>,
    wind_cap: vec4<f32>, relaxation: vec4<f32>, counts: vec4<u32>, detail: vec4<u32>,
}
struct Cell { velocity: vec4<f32>, scalar: vec4<f32> }
struct Emitter { position_radius: vec4<f32>, direction_length: vec4<f32>, rates: vec4<f32> }
struct Obstacle { a_radius: vec4<f32>, b_kind: vec4<f32>, velocity_enabled: vec4<f32> }
struct Controls { emitters: array<Emitter,32>, obstacles: array<Obstacle,32> }
struct Counters { invalid: atomic<u32>, clamps: atomic<u32> }
@group(0) @binding(0) var<uniform> cfg: Params;
@group(0) @binding(1) var<storage,read> controls: Controls;
@group(0) @binding(2) var<storage,read> source: array<Cell>;
@group(0) @binding(3) var<storage,read_write> output_cells: array<Cell>;
@group(0) @binding(4) var<storage,read> prediction: array<Cell>;
@group(0) @binding(5) var<storage,read_write> auxiliary: array<vec4<f32>>;
@group(0) @binding(6) var<storage,read_write> counters: Counters;

fn grid_index(c:vec3<u32>)->u32 {return c.x+(cfg.grid.x+1u)*(c.y+(cfg.grid.y+1u)*c.z);}
fn grid_coord(i:u32)->vec3<u32>{let q=i/(cfg.grid.x+1u);return vec3<u32>(i%(cfg.grid.x+1u),q%(cfg.grid.y+1u),q/(cfg.grid.y+1u));}
fn interior(c:vec3<i32>)->bool{return all(c>=vec3<i32>(0))&&all(c<vec3<i32>(cfg.grid.xyz));}
fn solid_at(c:vec3<i32>)->bool{if(!interior(c)){return false;}return source[grid_index(vec3<u32>(c))].scalar.w>0.5;}
fn centre(c:vec3<u32>)->vec3<f32>{return vec3<f32>(c)+vec3<f32>(0.5);}
fn face(c:vec3<u32>,a:u32)->vec3<f32>{var p=centre(c);p[a]-=0.5;return p;}
fn valid_face(c:vec3<u32>,a:u32)->bool{var n=cfg.grid.xyz;n[a]+=1u;return all(c<n);}
fn unit_axis(a:u32)->vec3<f32>{var v=vec3<f32>(0.0);v[a]=1.0;return v;}
fn world(p:vec3<f32>)->vec3<f32>{return cfg.origin_dx.xyz+p*cfg.origin_dx.w;}
fn smooth01(x:f32)->f32{let t=clamp(x,0.0,1.0);return t*t*(3.0-2.0*t);}
fn obstacle_sdf(o:Obstacle,p:vec3<f32>)->f32{
    if(o.velocity_enabled.w<0.5){return 1e30;}
    if(o.b_kind.w<0.5){let ba=o.b_kind.xyz-o.a_radius.xyz;let pa=p-o.a_radius.xyz;let h=clamp(dot(pa,ba)/max(dot(ba,ba),1e-12),0.0,1.0);return length(pa-ba*h)-o.a_radius.w;}
    let q=abs(p-(o.a_radius.xyz+o.b_kind.xyz)*0.5)-(o.b_kind.xyz-o.a_radius.xyz)*0.5;
    return length(max(q,vec3<f32>(0.0)))+min(max(q.x,max(q.y,q.z)),0.0);
}
fn wall_velocity(p:vec3<f32>)->vec3<f32>{var d=1e30;var v=vec3<f32>(0.0);for(var i=0u;i<32u;i++){let o=controls.obstacles[i];let q=obstacle_sdf(o,p);if(q<d){d=q;v=o.velocity_enabled.xyz;}}return v;}
fn physical_length(e:Emitter)->f32{return select(e.position_radius.w,e.direction_length.w,e.direction_length.w>0.0);}
fn density_scale(e:Emitter,dx:f32)->f32{
    let l=physical_length(e);let r=e.position_radius.w/max(e.position_radius.w,dx*1.1);return r*r*(l/max(l,dx));
}
fn source_weight(e:Emitter,p:vec3<f32>)->f32{
    if(e.rates.w<0.5){return 0.0;}let dx=cfg.origin_dx.w;let q=p-e.position_radius.xyz;
    let along=dot(q,e.direction_length.xyz);let extent=max(physical_length(e),dx);let radius=max(e.position_radius.w,dx*1.1);
    if(along< -dx*0.5||along>extent+dx*0.5){return 0.0;}
    let radial=length(q-e.direction_length.xyz*along);
    return (1.0-smooth01(radial/radius))*smooth01((along+dx*0.5)/dx)*smooth01((extent+dx*0.5-along)/dx);
}
fn value_at(c:vec3<u32>,a:u32,velocity:bool,predicted:bool)->f32{
    var cell=source[grid_index(c)];if(predicted){cell=prediction[grid_index(c)];}
    if(velocity){return cell.velocity[a];}return cell.scalar[a];
}
fn sample_value(p:vec3<f32>,a:u32,velocity:bool,predicted:bool)->f32{
    if(!velocity&&(any(p<vec3<f32>(0.0))||any(p>vec3<f32>(cfg.grid.xyz)))){return 0.0;}
    var upper=cfg.grid.xyz-vec3<u32>(1u);var offset=vec3<f32>(0.5);
    if(velocity){upper[a]+=1u;offset[a]=0.0;}
    let q=clamp(p-offset,vec3<f32>(0.0),vec3<f32>(upper));let b=vec3<u32>(floor(q));let f=q-vec3<f32>(b);var result=0.0;
    for(var z=0u;z<2u;z++){for(var y=0u;y<2u;y++){for(var x=0u;x<2u;x++){
        let d=vec3<u32>(x,y,z);let w=select(vec3<f32>(1.0)-f,f,d!=vec3<u32>(0u));
        result+=w.x*w.y*w.z*value_at(min(b+d,upper),a,velocity,predicted);
    }}}return result;
}
fn velocity_at(p:vec3<f32>)->vec3<f32>{return vec3<f32>(sample_value(p,0u,true,false),sample_value(p,1u,true,false),sample_value(p,2u,true,false));}
fn extrema(p:vec3<f32>,a:u32,velocity:bool)->vec2<f32>{
    var upper=vec3<i32>(cfg.grid.xyz)-vec3<i32>(1);var offset=vec3<f32>(0.5);if(velocity){upper[a]+=1;offset[a]=0.0;}
    let b=vec3<i32>(floor(p-offset));var low=1e30;var high= -1e30;
    for(var z=0;z<2;z++){for(var y=0;y<2;y++){for(var x=0;x<2;x++){
        let c=vec3<u32>(clamp(b+vec3<i32>(x,y,z),vec3<i32>(0),upper));let v=value_at(c,a,velocity,false);low=min(low,v);high=max(high,v);
    }}}return vec2<f32>(low,high);
}
fn trace(p:vec3<f32>,dt:f32)->vec3<f32>{
    let k=dt/cfg.origin_dx.w;let mid=p-velocity_at(p)*(0.5*k);let end=p-velocity_at(mid)*k;
    var occupied=false;for(var o=0u;o<32u;o++){occupied=occupied||controls.obstacles[o].velocity_enabled.w>0.5;}if(!occupied){return end;}
    let difference=end-p;let count=u32(clamp(ceil(length(difference)*2.0),1.0,64.0));var last=p;
    for(var j=1u;j<=count;j++){let q=p+difference*(f32(j)/f32(count));if(solid_at(vec3<i32>(floor(q)))){return last;}last=q;}return end;
}
fn confinement(c:vec3<u32>)->vec3<f32>{
    if(any(c==vec3<u32>(0u))||any(c+vec3<u32>(1u)>=cfg.grid.xyz)){return vec3<f32>(0.0);}
    var g=vec3<f32>(0.0);for(var a=0u;a<3u;a++){var lo=c;var hi=c;lo[a]-=1u;hi[a]+=1u;g[a]=auxiliary[grid_index(hi)].w-auxiliary[grid_index(lo)].w;}
    return cross(g/(length(g)+1e-6),auxiliary[grid_index(c)].xyz)*(cfg.physics.z*cfg.origin_dx.w);
}
@compute @workgroup_size(64) fn classify(@builtin(global_invocation_id) gid:vec3<u32>){
    let i=gid.x;if(i>=cfg.grid.w){return;}let c=grid_coord(i);var v=source[i];
    if(any(c>=cfg.grid.xyz)){v.scalar=vec4<f32>(0.0);}else{
        var solid=false;for(var o=0u;o<32u;o++){solid=solid||obstacle_sdf(controls.obstacles[o],world(centre(c)))<0.0;}
        v.scalar.w=select(0.0,1.0,solid);if(solid){v.scalar.x=0.0;v.scalar.y=0.0;v.scalar.z=0.0;}
    }output_cells[i]=v;
}
@compute @workgroup_size(64) fn force(@builtin(global_invocation_id) gid:vec3<u32>){
    let i=gid.x;if(i>=cfg.grid.w){return;}let c=grid_coord(i);var result=source[i];let dt=cfg.step.x;
    for(var a=0u;a<3u;a++){if(!valid_face(c,a)){result.velocity[a]=0.0;continue;}let p=face(c,a);var v=source[i].velocity[a];
        v+=(cfg.wind_cap[a]-v)*(1.0-exp(-cfg.physics.y*dt));
        if(a==1u){v+=dt*(cfg.step.w*sample_value(p,1u,false,false)-cfg.physics.x*sample_value(p,0u,false,false));}
        for(var e=0u;e<32u;e++){let emitter=controls.emitters[e];let w=source_weight(emitter,world(p));let gain=1.0-exp(-20.0*w*dt);v+=(emitter.direction_length[a]*emitter.rates.x-v)*gain;}
        result.velocity[a]=v;
    }output_cells[i]=result;
}
@compute @workgroup_size(64) fn curl(@builtin(global_invocation_id) gid:vec3<u32>){
    let i=gid.x;if(i>=cfg.grid.w){return;}let c=grid_coord(i);if(any(c>=cfg.grid.xyz)){auxiliary[i]=vec4<f32>(0.0);return;}
    let p=centre(c);let inv=0.5/cfg.origin_dx.w;
    let dx=(velocity_at(p+unit_axis(0u))-velocity_at(p-unit_axis(0u)))*inv;
    let dy=(velocity_at(p+unit_axis(1u))-velocity_at(p-unit_axis(1u)))*inv;
    let dz=(velocity_at(p+unit_axis(2u))-velocity_at(p-unit_axis(2u)))*inv;
    let w=vec3<f32>(dy.z-dz.y,dz.x-dx.z,dx.y-dy.x);auxiliary[i]=vec4<f32>(w,length(w));
}
@compute @workgroup_size(64) fn vorticity(@builtin(global_invocation_id) gid:vec3<u32>){
    let i=gid.x;if(i>=cfg.grid.w){return;}let c=grid_coord(i);var result=source[i];let f=confinement(c);
    for(var a=0u;a<3u;a++){if(c[a]>0u&&valid_face(c,a)){var lo=c;lo[a]-=1u;result.velocity[a]+=cfg.step.x*0.5*(f[a]+confinement(lo)[a]);}}output_cells[i]=result;
}
fn count_clamp(){var old=atomicLoad(&counters.clamps);loop{if(old==0xffffffffu){break;}let result=atomicCompareExchangeWeak(&counters.clamps,old,old+1u);if(result.exchanged){break;}old=result.old_value;}}
@compute @workgroup_size(64) fn limit_state(@builtin(global_invocation_id) gid:vec3<u32>){
    let i=gid.x;if(i>=cfg.grid.w){return;}var v=source[i];
    if(!all(abs(v.velocity)<=vec4<f32>(3.402823e38))||!all(abs(v.scalar)<=vec4<f32>(3.402823e38))){
        atomicOr(&counters.invalid,1u);v.velocity=vec4<f32>(0.0);v.scalar=vec4<f32>(0.0);
    }
    for(var a=0u;a<3u;a++){if(abs(v.velocity[a])>cfg.physics.w){v.velocity[a]=clamp(v.velocity[a],-cfg.physics.w,cfg.physics.w);count_clamp();}}output_cells[i]=v;
}
@compute @workgroup_size(64) fn advect_velocity(@builtin(global_invocation_id) gid:vec3<u32>){
    let i=gid.x;if(i>=cfg.grid.w){return;}let c=grid_coord(i);var result=source[i];
    for(var a=0u;a<3u;a++){if(valid_face(c,a)){result.velocity[a]=sample_value(trace(face(c,a),cfg.step.x),a,true,false);}}output_cells[i]=result;
}
@compute @workgroup_size(64) fn correct_velocity(@builtin(global_invocation_id) gid:vec3<u32>){
    let i=gid.x;if(i>=cfg.grid.w){return;}let c=grid_coord(i);var result=source[i];
    for(var a=0u;a<3u;a++){if(valid_face(c,a)){
        let p=face(c,a);let back=trace(p,cfg.step.x);let forward=trace(p,-cfg.step.x);
        let predicted=prediction[i].velocity[a];let q=predicted+0.5*(source[i].velocity[a]-sample_value(forward,a,true,true));
        let limits=extrema(back,a,true);let gain=min(2.0/max(length(back-p),1.0),1.0);
        result.velocity[a]=predicted+gain*(clamp(q,limits.x,limits.y)-predicted);
    }}output_cells[i]=result;
}
fn apply_boundary(i:u32,extrapolate:bool){
    let c=grid_coord(i);var result=source[i];
    for(var a=0u;a<3u;a++){if(!valid_face(c,a)){result.velocity[a]=0.0;continue;}
        let hi=vec3<i32>(c);var lo=hi;lo[a]-=1;
        if(solid_at(hi)||solid_at(lo)){result.velocity[a]=wall_velocity(world(face(c,a)))[a];continue;}
        if(c[a]==0u||c[a]==cfg.grid[a]){
            if(cfg.counts.z==1u){result.velocity[a]=0.0;}else{
                var v=source[i].velocity[a];if(extrapolate){var q=c;q[a]=select(cfg.grid[a]-1u,1u,c[a]==0u);v=source[grid_index(q)].velocity[a];}
                // Preserve pressure-driven ambient inflow; post-project clipping breaks divergence.
                result.velocity[a]=v;
                if(extrapolate){result.velocity[a]=select(max(v,0.0),min(v,0.0),c[a]==0u);}
            }
        }
    }output_cells[i]=result;
}
@compute @workgroup_size(64) fn boundary_pre(@builtin(global_invocation_id) gid:vec3<u32>){if(gid.x<cfg.grid.w){apply_boundary(gid.x,true);}}
@compute @workgroup_size(64) fn boundary_post(@builtin(global_invocation_id) gid:vec3<u32>){if(gid.x<cfg.grid.w){apply_boundary(gid.x,false);}}
@compute @workgroup_size(64) fn divergence(@builtin(global_invocation_id) gid:vec3<u32>){
    let i=gid.x;if(i>=cfg.grid.w){return;}let c=grid_coord(i);var result=source[i];result.scalar.z=0.0;var d=0.0;
    if(all(c<cfg.grid.xyz)&&result.scalar.w<0.5){for(var a=0u;a<3u;a++){var hi=c;hi[a]+=1u;d+=source[grid_index(hi)].velocity[a]-source[i].velocity[a];}d/=cfg.origin_dx.w;}
    auxiliary[i].w=d;output_cells[i]=result;
}
fn sor_half(i:u32,colour:u32){
    let c=grid_coord(i);if(any(c>=cfg.grid.xyz)||((c.x+c.y+c.z)&1u)!=colour||output_cells[i].scalar.w>0.5){return;}
    var sum=0.0;var count=0.0;
    for(var a=0u;a<3u;a++){for(var side=0u;side<2u;side++){var q=vec3<i32>(c);q[a]+=select(-1,1,side==1u);
        if(interior(q)){let neighbour=grid_index(vec3<u32>(q));if(output_cells[neighbour].scalar.w<=0.5){sum+=output_cells[neighbour].scalar.z;count+=1.0;}}
        else if(cfg.counts.z==0u){count+=1.0;}
    }}if(count>0.0){let next=(sum-auxiliary[i].w*cfg.origin_dx.w*cfg.origin_dx.w)/count;output_cells[i].scalar.z+=cfg.relaxation.x*(next-output_cells[i].scalar.z);}
}
@compute @workgroup_size(64) fn sor_red(@builtin(global_invocation_id) gid:vec3<u32>){if(gid.x<cfg.grid.w){sor_half(gid.x,0u);}}
@compute @workgroup_size(64) fn sor_black(@builtin(global_invocation_id) gid:vec3<u32>){if(gid.x<cfg.grid.w){sor_half(gid.x,1u);}}
fn pressure(c:vec3<i32>)->f32{if(!interior(c)){return 0.0;}return source[grid_index(vec3<u32>(c))].scalar.z;}
@compute @workgroup_size(64) fn project(@builtin(global_invocation_id) gid:vec3<u32>){
    let i=gid.x;if(i>=cfg.grid.w){return;}let c=grid_coord(i);var result=source[i];
    for(var a=0u;a<3u;a++){if(!valid_face(c,a)){continue;}let hi=vec3<i32>(c);var lo=hi;lo[a]-=1;
        if(solid_at(hi)||solid_at(lo)){result.velocity[a]=wall_velocity(world(face(c,a)))[a];continue;}
        if(cfg.counts.z==1u&&(!interior(hi)||!interior(lo))){result.velocity[a]=0.0;continue;}
        result.velocity[a]-=(pressure(hi)-pressure(lo))/cfg.origin_dx.w;
    }output_cells[i]=result;
}
@compute @workgroup_size(64) fn advect_scalar(@builtin(global_invocation_id) gid:vec3<u32>){
    let i=gid.x;if(i>=cfg.grid.w){return;}let c=grid_coord(i);var result=source[i];
    if(all(c<cfg.grid.xyz)){let p=trace(centre(c),cfg.step.x);result.scalar.x=sample_value(p,0u,false,false);result.scalar.y=sample_value(p,1u,false,false);}output_cells[i]=result;
}
@compute @workgroup_size(64) fn correct_scalar(@builtin(global_invocation_id) gid:vec3<u32>){
    let i=gid.x;if(i>=cfg.grid.w){return;}let c=grid_coord(i);var result=source[i];
    if(any(c>=cfg.grid.xyz)||result.scalar.w>0.5){result.scalar.x=0.0;result.scalar.y=0.0;output_cells[i]=result;return;}
    let p=centre(c);let back=trace(p,cfg.step.x);let forward=trace(p,-cfg.step.x);let gain=min(2.0/max(length(back-p),1.0),1.0);
    for(var a=0u;a<2u;a++){
        if(any(back<vec3<f32>(0.0))||any(back>vec3<f32>(cfg.grid.xyz))){result.scalar[a]=0.0;continue;}
        let predicted=prediction[i].scalar[a];let q=predicted+0.5*(source[i].scalar[a]-sample_value(forward,a,false,true));let limits=extrema(back,a,false);
        result.scalar[a]=max(predicted+gain*(clamp(q,limits.x,limits.y)-predicted),0.0);
    }
    result.scalar.x*=exp(-cfg.step.y*cfg.step.x);result.scalar.y*=exp(-cfg.step.z*cfg.step.x);
    for(var e=0u;e<32u;e++){let emitter=controls.emitters[e];let w=source_weight(emitter,world(p));result.scalar.x+=emitter.rates.y*w*density_scale(emitter,cfg.origin_dx.w)*cfg.step.x;result.scalar.y+=max(emitter.rates.z-result.scalar.y,0.0)*(1.0-exp(-20.0*w*cfg.step.x));}
    result.scalar.x=min(result.scalar.x,cfg.wind_cap.w);output_cells[i]=result;
}
