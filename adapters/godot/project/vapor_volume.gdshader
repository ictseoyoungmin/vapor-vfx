shader_type spatial;
render_mode unshaded, cull_front, depth_draw_never, depth_test_disabled, blend_mix;
uniform sampler2D density_atlas : filter_linear, repeat_disable;
uniform sampler2D scene_depth : hint_depth_texture, filter_nearest, repeat_disable;
uniform vec3 cells = vec3(16.,20.,16.);
uniform vec3 extent_m = vec3(.64,.8,.64);
uniform float density_cap = 8.;
uniform float extinction = 5.;
uniform int ray_steps = 72;
uniform vec3 smoke_colour : source_color = vec3(.78,.83,.9);
uniform float anisotropy = 0.;
uniform float albedo = 1.;
uniform float ambient = .35;
uniform float emission = 0.;
uniform float thermal_fade = 0.;
varying vec3 local_position;
varying vec3 eye_local;
varying mat4 world_to_local;
void vertex(){
 local_position=VERTEX+.5;
 world_to_local=inverse(MODEL_MATRIX);
 eye_local=(world_to_local*vec4(CAMERA_POSITION_WORLD,1.)).xyz+.5;
}
vec2 sample_field(vec3 p){
 if(any(lessThan(p,vec3(0.)))||any(greaterThan(p,vec3(1.))))return vec2(0.);
 vec3 q=clamp(p*cells-.5,vec3(0.),cells-1.);float z=floor(q.z);float z1=min(z+1.,cells.z-1.);
 vec2 uv=vec2((q.x+.5)/cells.x,(q.y+.5+z*cells.y)/(cells.y*cells.z));
 vec2 uv1=vec2(uv.x,(q.y+.5+z1*cells.y)/(cells.y*cells.z));
 return mix(textureLod(density_atlas,uv,0.).rg,textureLod(density_atlas,uv1,0.).rg,fract(q.z));
}
float density(vec3 p){vec2 f=sample_field(p);return f.r*density_cap*(1.-thermal_fade*(1.-exp(-f.g*16.)));}
void fragment(){
 vec3 rd=normalize(local_position-eye_local);vec3 safe=rd;
 for(int k=0;k<3;k++){if(abs(safe[k])<.000001)safe[k]=safe[k]<0.?-.000001:.000001;}
 vec3 a=(vec3(0.)-eye_local)/safe;vec3 b=(vec3(1.)-eye_local)/safe;
 vec3 nearv=min(a,b);vec3 farv=max(a,b);float t0=max(0.,max(nearv.x,max(nearv.y,nearv.z)));float t1=min(farv.x,min(farv.y,farv.z));
 float d=textureLod(scene_depth,SCREEN_UV,0.).r;
 #if CURRENT_RENDERER == RENDERER_COMPATIBILITY
 vec3 ndc=vec3(SCREEN_UV,d)*2.-1.;
 #else
 vec3 ndc=vec3(SCREEN_UV*2.-1.,d);
 #endif
 vec4 view_pos=INV_PROJECTION_MATRIX*vec4(ndc,1.);
 if(abs(view_pos.w)>.000001){view_pos/=view_pos.w;vec4 wp=INV_VIEW_MATRIX*view_pos;vec3 lp=(world_to_local*wp).xyz+.5;t1=min(t1,dot(lp-eye_local,rd));}
 if(t1<=t0)discard;
 float dt=(t1-t0)/float(ray_steps);float ds=dt*length(rd*extent_m);float transmission=1.;vec3 light_dir=normalize(vec3(-.4,.8,.2));vec3 illum=vec3(0.);float shadow_step=min(extent_m.x,min(extent_m.y,extent_m.z))/8.;float g=clamp(anisotropy,-.9,.9);float phase=min(4.,(1.-g*g)/pow(max(.001,1.+g*g-2.*g*dot(normalize(rd*extent_m),light_dir)),1.5));
 for(int i=0;i<256;i++){if(i>=ray_steps||transmission<.01)break;vec3 p=eye_local+rd*(t0+(float(i)+.5)*dt);float den=density(p);float alpha=1.-exp(-den*extinction*ds);float shadow=0.;
  for(int j=1;j<=8;j++)shadow+=density(p+light_dir*(float(j)*shadow_step)/extent_m)*shadow_step;
  float heat=clamp(sample_field(p).g*16./5.,0.,1.);illum+=transmission*alpha*(smoke_colour*albedo*(ambient+(1.-ambient)*exp(-shadow*extinction)*phase)+vec3(1.,.3,.045)*emission*heat*heat);transmission*=1.-alpha;}
 ALPHA=1.-transmission;ALBEDO=illum/max(ALPHA,.00001);
}
