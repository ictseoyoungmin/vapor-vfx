// Same-device temporal resolve and composition. All history remains in GPU textures.
// Anchors are opacity-weighted points in normalized local domain coordinates, NOT opaque depth.
struct ViewParams {
    grid:vec4<u32>, extent:vec4<f32>, eye:vec4<f32>, forward:vec4<f32>,
    right:vec4<f32>, up:vec4<f32>, colour_extinction:vec4<f32>, optical:vec4<f32>,
    light_ambient:vec4<f32>, render_options:vec4<u32>,
}
struct TemporalParams {
    current:ViewParams, previous:ViewParams,
    // valid flag, maximum blend weight, anchor tolerance (metres), raw alpha tolerance
    control:vec4<f32>,
}
@group(0) @binding(0) var<uniform> params:TemporalParams;
@group(0) @binding(1) var current_layer:texture_2d<f32>;
@group(0) @binding(2) var current_geometry:texture_2d<f32>;
@group(0) @binding(3) var history_layer:texture_2d<f32>;
@group(0) @binding(4) var history_geometry:texture_2d<f32>;
struct VertexOutput { @builtin(position) position:vec4<f32>, @location(0) ndc:vec2<f32> }
@vertex fn vertex_main(@builtin(vertex_index) i:u32)->VertexOutput{
    let xy=vec2<f32>(f32((i<<1u)&2u),f32(i&2u))*2.0-vec2<f32>(1.0);
    var out:VertexOutput;out.position=vec4<f32>(xy,0.0,1.0);out.ndc=xy;return out;
}
@fragment fn resolve_main(v:VertexOutput)->@location(0) vec4<f32>{
    let size=vec2<i32>(textureDimensions(current_layer,0));
    let coord=clamp(vec2<i32>(v.position.xy),vec2<i32>(0),size-vec2<i32>(1));
    let raw=textureLoad(current_layer,coord,0);
    // A pixel with no current opacity must never inherit a previous plume.
    if(params.control.x<0.5||raw.a<0.003){return raw;}
    let geo=textureLoad(current_geometry,coord,0);
    let local=geo.xyz*params.current.extent.xyz;
    let rel=local-params.previous.eye.xyz;
    let depth=dot(rel,params.previous.forward.xyz);
    if(depth<=1e-5){return raw;}
    let uv=vec2<f32>(0.5+0.5*dot(rel,params.previous.right.xyz)/(depth*params.previous.forward.w*params.previous.right.w),
                    0.5-0.5*dot(rel,params.previous.up.xyz)/(depth*params.previous.forward.w));
    if(any(uv<vec2<f32>(0.0))||any(uv>vec2<f32>(1.0))){return raw;}
    // Manual bilinear gather; reject each tap independently before interpolation.
    let q=uv*vec2<f32>(size)-vec2<f32>(0.5);let base=vec2<i32>(floor(q));let fraction=fract(q);
    var accumulated=vec4<f32>(0.0);var coverage=0.0;
    for(var y=0;y<2;y++){
        for(var x=0;x<2;x++){
            let c=base+vec2<i32>(x,y);
            if(any(c<vec2<i32>(0))||any(c>=size)){continue;}
            let old_geo=textureLoad(history_geometry,c,0);
            if(old_geo.a<0.003||abs(old_geo.a-geo.a)>params.control.w){continue;}
            let delta=(old_geo.xyz-geo.xyz)*params.current.extent.xyz;
            if(length(delta)>params.control.z){continue;}
            let weight=select(1.0-fraction.x,fraction.x,x==1)*select(1.0-fraction.y,fraction.y,y==1);
            accumulated+=weight*textureLoad(history_layer,c,0);coverage+=weight;
        }
    }
    if(coverage<0.25){return raw;}
    // Clamp previous premultiplied radiance and opacity to CURRENT local range.
    var lo=raw;var hi=raw;
    for(var y=-1;y<=1;y++){
        for(var x=-1;x<=1;x++){
            let sample_value=textureLoad(current_layer,clamp(coord+vec2<i32>(x,y),vec2<i32>(0),size-vec2<i32>(1)),0);
            lo=min(lo,sample_value);hi=max(hi,sample_value);
        }
    }
    let old=clamp(accumulated/coverage,lo,hi);
    return mix(raw,old,params.control.y*min(coverage,1.0));
}
// In this entry point binding 1 is the freshly resolved layer. No background
// from any earlier frame is stored or reused. Target may be a host colour view.
@fragment fn composite_main(v:VertexOutput)->@location(0) vec4<f32>{
    let size=vec2<i32>(textureDimensions(current_layer,0));
    let uv=vec2<f32>(0.5+0.5*v.ndc.x,0.5-0.5*v.ndc.y);
    let coord=clamp(vec2<i32>(uv*vec2<f32>(size)),vec2<i32>(0),size-vec2<i32>(1));
    let layer=textureLoad(current_layer,coord,0);
    if(params.current.render_options.z==0u){return layer;}
    let d=normalize(params.current.forward.xyz+params.current.right.xyz*(v.ndc.x*params.current.forward.w*params.current.right.w)+params.current.up.xyz*(v.ndc.y*params.current.forward.w));
    var bg=vec3<f32>(0.012,0.02,0.035);
    if(params.current.render_options.z==2u){bg=vec3<f32>(0.20,0.39,0.64)+clamp(-d.y,0.0,1.0)*vec3<f32>(0.15,0.15,0.11);}
    return vec4<f32>(layer.rgb+(1.0-layer.a)*bg,1.0);
}
