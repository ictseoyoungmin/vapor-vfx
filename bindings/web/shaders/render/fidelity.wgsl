// Append to volume.wgsl. Optional high fidelity direct renderer, using the same
// borrowed Float32 MAC/detail buffer. Separate compute and render bindings for cache.
struct FidelityLighting {
    cache_grid: vec4<u32>, // xyz dimensions, w sunlight quadrature steps
    sun_multi: vec4<f32>, // linear sun radiance, multiple scattering approximation
    sky_exposure: vec4<f32>, // linear sky radiance, standalone display exposure
    ground_light: vec4<f32>,
}
@group(0) @binding(3) var<uniform> fidelity: FidelityLighting;
@group(0) @binding(4) var<storage,read_write> cache_write: array<vec4<f32>>;
@group(0) @binding(5) var<storage,read> cache_read: array<vec4<f32>>;
fn f_index(c:vec3<u32>)->u32 {return c.x+fidelity.cache_grid.x*(c.y+fidelity.cache_grid.y*c.z);}
fn f_coord(i:u32)->vec3<u32> {let g=fidelity.cache_grid.xyz;return vec3<u32>(i%g.x,(i/g.x)%g.y,i/(g.x*g.y));}
fn f_position(c:vec3<u32>)->vec3<f32> {return (vec3<f32>(c)+vec3<f32>(0.5))/vec3<f32>(fidelity.cache_grid.xyz)*view.extent.xyz;}
fn f_cell(c:vec3<u32>)->vec2<f32> {let s=scalar_at(c);return vec2<f32>(effective_density(s),s.y);}
// Thermal attenuation precedes interpolation, matching the CPU fidelity reference.
fn f_sample(p:vec3<f32>)->vec2<f32>{
    if(any(p<vec3<f32>(0.0))||any(p>view.extent.xyz)){return vec2<f32>(0.0);}
    let hi=view.grid.xyz-vec3<u32>(1u);
    let q=clamp(p/view.extent.xyz*vec3<f32>(view.grid.xyz)-vec3<f32>(0.5),vec3<f32>(0.0),vec3<f32>(hi));
    let a=vec3<u32>(floor(q));let b=min(a+vec3<u32>(1u),hi);let f=fract(q);
    return mix(mix(mix(f_cell(a),f_cell(vec3<u32>(b.x,a.y,a.z)),f.x),mix(f_cell(vec3<u32>(a.x,b.y,a.z)),f_cell(vec3<u32>(b.x,b.y,a.z)),f.x),f.y),mix(mix(f_cell(vec3<u32>(a.x,a.y,b.z)),f_cell(vec3<u32>(b.x,a.y,b.z)),f.x),mix(f_cell(vec3<u32>(a.x,b.y,b.z)),f_cell(b),f.x),f.y),f.z);
}
@compute @workgroup_size(64) fn fidelity_sun_cache(@builtin(global_invocation_id) gid:vec3<u32>){
    let g=fidelity.cache_grid.xyz;let i=gid.x;if(i>=g.x*g.y*g.z){return;}
    let p=f_position(f_coord(i));let d=view.light_ambient.xyz;let hit=intersect_box(p,d);
    let ds=max(hit.y,0.0)/f32(fidelity.cache_grid.w);var tau=0.0;
    for(var j=0u;j<fidelity.cache_grid.w;j++) {tau+=f_sample(p+d*((f32(j)+0.5)*ds)).x*ds*view.colour_extinction.w;}
    cache_write[i]=vec4<f32>(tau,0.0,0.0,0.0);
}
// One invocation per xz column. Exact midpoint prefix integration on cache grid,
// O(ny) work, no cross-column writes, no inter-workgroup synchronization needed.
@compute @workgroup_size(64) fn fidelity_vertical_cache(@builtin(global_invocation_id) gid:vec3<u32>){
    let g=fidelity.cache_grid.xyz;let i=gid.x;if(i>=g.x*g.z){return;}
    let x=i%g.x;let z=i/g.x;let ds=view.extent.y/f32(g.y)*view.colour_extinction.w;
    var running=0.0;
    for(var y=0u;y<g.y;y++){
        let c=vec3<u32>(x,y,z);let idx=f_index(c);let delta=f_sample(f_position(c)).x*ds;
        var entry=cache_write[idx];entry.z=running+0.5*delta;entry.w=delta;cache_write[idx]=entry;running+=delta;
    }
    running=0.0;
    for(var k=0u;k<g.y;k++){
        let y=g.y-1u-k;let idx=f_index(vec3<u32>(x,y,z));var entry=cache_write[idx];entry.y=running+0.5*entry.w;running+=entry.w;cache_write[idx]=entry;
    }
}
fn f_cache(p:vec3<f32>)->vec3<f32>{
    let hi=fidelity.cache_grid.xyz-vec3<u32>(1u);let q=clamp(p/view.extent.xyz*vec3<f32>(fidelity.cache_grid.xyz)-vec3<f32>(0.5),vec3<f32>(0.0),vec3<f32>(hi));
    let a=vec3<u32>(floor(q));let b=min(a+vec3<u32>(1u),hi);let f=fract(q);
    let v00=mix(cache_read[f_index(a)].xyz,cache_read[f_index(vec3<u32>(b.x,a.y,a.z))].xyz,f.x);
    let v10=mix(cache_read[f_index(vec3<u32>(a.x,b.y,a.z))].xyz,cache_read[f_index(vec3<u32>(b.x,b.y,a.z))].xyz,f.x);
    let v01=mix(cache_read[f_index(vec3<u32>(a.x,a.y,b.z))].xyz,cache_read[f_index(vec3<u32>(b.x,a.y,b.z))].xyz,f.x);
    let v11=mix(cache_read[f_index(vec3<u32>(a.x,b.y,b.z))].xyz,cache_read[f_index(b)].xyz,f.x);
    return mix(mix(v00,v10,f.y),mix(v01,v11,f.y),f.z);
}
fn f_hg(g:f32,c:f32)->f32{return (1.0-g*g)/pow(max(1e-5,1.0+g*g-2.0*g*c),1.5);}
fn f_phase(g:f32,c:f32)->f32{return 0.88*f_hg(g,c)+0.12*f_hg(-g*0.38,c);}
fn f_integrate(d:vec3<f32>,limit:f32)->vec4<f32>{
    var hit=intersect_box(view.eye.xyz,d);hit.y=min(hit.y,limit);
    var tr=1.0;var rgb=vec3<f32>(0.0);let g=view.optical.x;let cos_angle=clamp(dot(d,view.light_ambient.xyz),-1.0,1.0);
    let p1=f_phase(g,cos_angle);let p2=f_phase(g*0.43,cos_angle);let p3=f_phase(g*0.15,cos_angle);
    if(hit.y>hit.x){let ds=(hit.y-hit.x)/f32(view.render_options.x);
        for(var j=0u;j<view.render_options.x;j++){
            let p=view.eye.xyz+d*(hit.x+(f32(j)+0.5)*ds);let s=f_sample(p);if(s.x<=1e-7){continue;}
            let a=1.0-exp(-s.x*view.colour_extinction.w*ds);let depth=f_cache(p);
            let albedo=view.optical.y;let sun=exp(-depth.x)*p1+fidelity.sun_multi.w*(0.50*albedo*exp(-0.33*depth.x)*p2+0.23*albedo*albedo*exp(-0.10*depth.x)*p3);
            let sky_vis=0.20*exp(-0.09*depth.y)+0.80*exp(-0.65*depth.y)+view.light_ambient.w*0.30;
            let illumination=fidelity.sun_multi.xyz*sun+fidelity.sky_exposure.xyz*sky_vis+fidelity.ground_light.xyz*exp(-0.23*depth.z);
            let heat=clamp(s.y/5.0,0.0,1.0);let emission=view.optical.z*heat*heat*vec3<f32>(1.0,0.3,0.045);
            rgb+=tr*a*(view.colour_extinction.xyz*albedo*illumination+emission);tr*=1.0-a;if(tr<0.0007){break;}
        }
    }return vec4<f32>(rgb,1.0-tr);
}
fn f_display(c:vec3<f32>)->vec3<f32>{let v=max(c*fidelity.sky_exposure.w,vec3<f32>(0.0));return clamp((v*(2.51*v+vec3<f32>(0.03)))/(v*(2.43*v+vec3<f32>(0.59))+vec3<f32>(0.14)),vec3<f32>(0.0),vec3<f32>(1.0));}
@fragment fn fidelity_fragment(v:VertexOutput)->@location(0) vec4<f32>{
    let d=ray_direction(v.ndc);let layer=f_integrate(d,1e20);if(view.render_options.z==0u){return layer;}
    var bg=vec3<f32>(0.004,0.006,0.010);
    if(view.render_options.z==2u){let horizon=pow(1.0-clamp(d.y*1.6,0.0,1.0),3.0);let glow=pow(max(0.0,dot(d,view.light_ambient.xyz)),24.0)*0.14;bg=mix(vec3<f32>(0.035,0.105,0.34),vec3<f32>(0.15,0.27,0.48),horizon)+glow*vec3<f32>(1.0,0.83,0.55);}
    return vec4<f32>(f_display(layer.rgb+(1.0-layer.a)*bg),1.0);
}
@fragment fn fidelity_fragment_depth(v:VertexOutput)->@location(0) vec4<f32>{
    let pixel=vec2<u32>(v.position.xy);if(any(pixel>=textureDimensions(scene_distance,0))){return vec4<f32>(0.0);}
    let distance=textureLoad(scene_distance,vec2<i32>(pixel),0).x;return f_integrate(ray_direction(v.ndc),select(1e20,distance,distance>0.0));
}
