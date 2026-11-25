// Read the current simulation field directly on the same WebGPU device.
// MAC: two vec4 per padded cell, scalar at +1. Detail: one vec4 per dense cell.
// Host supplies positions local to the domain in metres; no readback or RGBA8 pack.
struct ViewParams {
    grid: vec4<u32>, // xyz = render dimensions, w = 0 MAC / 1 detail
    extent: vec4<f32>, // xyz metres
    eye: vec4<f32>,
    forward: vec4<f32>, // w = tan(vertical_fov/2)
    right: vec4<f32>, // w = aspect
    up: vec4<f32>,
    colour_extinction: vec4<f32>,
    optical: vec4<f32>, // anisotropy, albedo, emission, thermalFade
    light_ambient: vec4<f32>,
    render_options: vec4<u32>, // steps, shadow steps, background (0 transparent/1 dark/2 sky), reserved
}
@group(0) @binding(0) var<uniform> view: ViewParams;
@group(0) @binding(1) var<storage,read> field_values: array<vec4<f32>>;
// Optional direct-only host texture. R32Float, ray distance in metres (0 = sky).
@group(0) @binding(2) var scene_distance: texture_2d<f32>;
struct VertexOutput { @builtin(position) position: vec4<f32>, @location(0) ndc: vec2<f32> }
@vertex fn vertex_main(@builtin(vertex_index) i:u32)->VertexOutput {
    let xy=vec2<f32>(f32((i<<1u)&2u),f32(i&2u))*2.0-vec2<f32>(1.0);
    var out:VertexOutput;out.position=vec4<f32>(xy,0.0,1.0);out.ndc=xy;return out;
}
fn scalar_at(c:vec3<u32>)->vec2<f32>{
    if(view.grid.w==1u){let i=c.x+view.grid.x*(c.y+view.grid.y*c.z);let s=field_values[i];return select(max(s.xy,vec2<f32>(0.0)),vec2<f32>(0.0),s.z>0.5);}
    let i=c.x+(view.grid.x+1u)*(c.y+(view.grid.y+1u)*c.z);let s=field_values[2u*i+1u];return select(max(s.xy,vec2<f32>(0.0)),vec2<f32>(0.0),s.w>0.5);
}
fn sample_field(p:vec3<f32>)->vec2<f32>{
    if(any(p<vec3<f32>(0.0))||any(p>view.extent.xyz)){return vec2<f32>(0.0);}
    let hi=view.grid.xyz-vec3<u32>(1u);
    let q=clamp(p/view.extent.xyz*vec3<f32>(view.grid.xyz)-vec3<f32>(0.5),vec3<f32>(0.0),vec3<f32>(hi));
    let a=vec3<u32>(floor(q));let b=min(a+vec3<u32>(1u),hi);let f=fract(q);
    let v00=mix(scalar_at(a),scalar_at(vec3<u32>(b.x,a.y,a.z)),f.x);
    let v10=mix(scalar_at(vec3<u32>(a.x,b.y,a.z)),scalar_at(vec3<u32>(b.x,b.y,a.z)),f.x);
    let v01=mix(scalar_at(vec3<u32>(a.x,a.y,b.z)),scalar_at(vec3<u32>(b.x,a.y,b.z)),f.x);
    let v11=mix(scalar_at(vec3<u32>(a.x,b.y,b.z)),scalar_at(b),f.x);
    return mix(mix(v00,v10,f.y),mix(v01,v11,f.y),f.z);
}
fn effective_density(s:vec2<f32>)->f32{return s.x*(1.0-view.optical.w*(1.0-exp(-s.y)));}
fn intersect_box(o:vec3<f32>,d:vec3<f32>)->vec2<f32>{
    var lo=0.0;var hi=1e20;
    for(var axis=0u;axis<3u;axis++){
        if(abs(d[axis])<1e-7){if(o[axis]<0.0||o[axis]>view.extent[axis]){return vec2<f32>(1.0,0.0);}}
        else{let a=-o[axis]/d[axis];let b=(view.extent[axis]-o[axis])/d[axis];lo=max(lo,min(a,b));hi=min(hi,max(a,b));}
    }return vec2<f32>(lo,hi);
}
fn light_transmittance(p:vec3<f32>)->f32{
    if(view.render_options.y==0u){return 1.0;}
    let d=view.light_ambient.xyz;let hit=intersect_box(p,d);let ds=max(hit.y,0.0)/f32(view.render_options.y);var tau=0.0;
    for(var i=0u;i<view.render_options.y;i++){
        tau+=effective_density(sample_field(p+d*((f32(i)+0.5)*ds)))*view.colour_extinction.w*ds;
        if(tau>8.0){break;}
    }return exp(-tau);
}
fn ray_direction(ndc:vec2<f32>)->vec3<f32>{
    return normalize(view.forward.xyz+view.right.xyz*(ndc.x*view.forward.w*view.right.w)+view.up.xyz*(ndc.y*view.forward.w));
}
struct VolumeIntegral { rgb:vec3<f32>, transmittance:f32, anchor:vec3<f32> }
fn integrate(d:vec3<f32>, jitter:f32, capture_anchor:bool, max_distance:f32)->VolumeIntegral{
    var hit=intersect_box(view.eye.xyz,d);hit.y=min(hit.y,max_distance);var tr=1.0;var rgb=vec3<f32>(0.0);var moment=0.0;
    let g=view.optical.x;let phase=min(4.0,(1.0-g*g)/pow(max(0.001,1.0+g*g-2.0*g*clamp(dot(d,view.light_ambient.xyz),-1.0,1.0)),1.5));
    if(hit.y>hit.x){
        let ds=(hit.y-hit.x)/f32(view.render_options.x);
        for(var i=0u;i<view.render_options.x;i++){
            let t=hit.x+(f32(i)+jitter)*ds;let p=view.eye.xyz+d*t;let s=sample_field(p);let den=effective_density(s);
            if(den>0.000001){
                let a=1.0-exp(-den*view.colour_extinction.w*ds);let heat=clamp(s.y/5.0,0.0,1.0);
                let lighting=view.optical.y*(view.light_ambient.w+(1.0-view.light_ambient.w)*light_transmittance(p)*phase);
                let contribution=tr*a;
                rgb+=contribution*(view.colour_extinction.xyz*lighting+view.optical.z*heat*heat*vec3<f32>(1.0,0.3,0.045));if(capture_anchor){moment+=contribution*t;}tr*=1.0-a;
                if(tr<0.003){break;}
            }
        }
    }
    var anchor=vec3<f32>(0.0);
    if(capture_anchor){let mean_distance=moment/max(1.0-tr,1e-8);anchor=clamp((view.eye.xyz+d*mean_distance)/view.extent.xyz,vec3<f32>(0.0),vec3<f32>(1.0));}
    return VolumeIntegral(rgb,tr,anchor);
}
@fragment fn fragment_main(v:VertexOutput)->@location(0) vec4<f32>{
    let d=ray_direction(v.ndc);let volume=integrate(d,0.5,false,1e20);let rgb=volume.rgb;let tr=volume.transmittance;
    // For transparent mode output premultiplied linear colour, suitable for composition.
    if(view.render_options.z==0u){return vec4<f32>(rgb,1.0-tr);}
    var bg=vec3<f32>(0.012,0.02,0.035);
    if(view.render_options.z==2u){bg=vec3<f32>(0.20,0.39,0.64)+clamp(-d.y,0.0,1.0)*vec3<f32>(0.15,0.15,0.11);}
    return vec4<f32>(rgb+tr*bg,1.0);
}

// Raw optical layer + opacity-weighted normalized local anchor. The host
// supplies a deterministic stratified ray offset, zero means midpoint.
struct TemporalOutput { @location(0) layer:vec4<f32>, @location(1) geometry:vec4<f32> }
@fragment fn temporal_march(v:VertexOutput)->TemporalOutput{
    let sample_index=view.render_options.w;
    var jitter=0.5;
    if(sample_index!=0u){jitter=(f32(((sample_index-1u)*5u)%8u)+0.5)/8.0;}
    let volume=integrate(ray_direction(v.ndc),jitter,true,1e20);let alpha=1.0-volume.transmittance;
    return TemporalOutput(vec4<f32>(volume.rgb,alpha),vec4<f32>(volume.anchor,alpha));
}

// Direct-only depth clipping. The host has already drawn opaque geometry into
// the colour attachment. Premultiplied output composites over that attachment.
@fragment fn fragment_scene_depth(v:VertexOutput)->@location(0) vec4<f32>{
    let pixel=vec2<u32>(v.position.xy);
    if(any(pixel>=textureDimensions(scene_distance,0))){return vec4<f32>(0.0);}
    let distance=textureLoad(scene_distance,vec2<i32>(pixel),0).x;
    let ray_limit=select(1e20,distance,distance>0.0);
    let volume=integrate(ray_direction(v.ndc),0.5,false,ray_limit);
    return vec4<f32>(volume.rgb,1.0-volume.transmittance);
}
