struct Params {grid:vec4<u32>,origin_dx:vec4<f32>,step:vec4<f32>,physics:vec4<f32>,wind_cap:vec4<f32>,relaxation:vec4<f32>,counts:vec4<u32>,detail:vec4<u32>}
struct Cell {velocity:vec4<f32>,scalar:vec4<f32>}
@group(0) @binding(0) var<uniform> cfg:Params;
@group(0) @binding(1) var<storage,read> coarse:array<Cell>;
@group(0) @binding(2) var<storage,read> detail:array<vec4<f32>>;
@group(0) @binding(3) var<storage,read_write> rgba:array<u32>;
fn pack(rho:f32,temp:f32,solid:f32)->u32{
    let r=u32(clamp(floor(rho/cfg.wind_cap.w*255.0+0.5),0.0,255.0));let g=u32(clamp(floor(temp/16.0*255.0+0.5),0.0,255.0));let b=select(0u,255u,solid>0.5);
    return r|(g<<8u)|(b<<16u)|0xff000000u;
}
@compute @workgroup_size(64) fn pack_main(@builtin(global_invocation_id) gid:vec3<u32>){
    let i=gid.x;if(i>=cfg.grid.x*cfg.grid.y*cfg.grid.z){return;}let c=vec3<u32>(i%cfg.grid.x,(i/cfg.grid.x)%cfg.grid.y,i/(cfg.grid.x*cfg.grid.y));let k=c.x+(cfg.grid.x+1u)*(c.y+(cfg.grid.y+1u)*c.z);let s=coarse[k].scalar;rgba[i]=pack(s.x,s.y,s.w);
}
@compute @workgroup_size(64) fn pack_detail(@builtin(global_invocation_id) gid:vec3<u32>){let i=gid.x;if(i>=cfg.detail.y*cfg.detail.z*cfg.detail.w){return;}let s=detail[i];rgba[i]=pack(s.x,s.y,s.z);}
