#include <godot_cpp/godot.hpp>
#include <godot_cpp/classes/ref_counted.hpp>
#include <godot_cpp/classes/image.hpp>
#include <godot_cpp/core/class_db.hpp>
#include <godot_cpp/variant/utility_functions.hpp>
#include <godot_cpp/variant/dictionary.hpp>
#include <godot_cpp/variant/array.hpp>
#include <godot_cpp/variant/packed_float32_array.hpp>
#include <godot_cpp/variant/packed_float64_array.hpp>
#include <godot_cpp/variant/packed_byte_array.hpp>
#include <godot_cpp/variant/vector3i.hpp>
#include "vapor.h"
#include "vapor_effect.hpp"
#include "vapor_atlas_stream.hpp"
#include <limits>
using namespace godot;
namespace {
void xyz(float* p,Vector3 v){p[0]=v.x;p[1]=v.y;p[2]=v.z;}
bool valid_id(int64_t id){return id>=0&&id<=std::numeric_limits<uint32_t>::max();}
}
// Main-thread facade. The Rust runtime serializes concurrent calls on the same handle.
class VaporSimulation : public RefCounted {
 GDCLASS(VaporSimulation,RefCounted);
 VaporHandle handle=0;VaporConfig config{};VaporBackendInfo backend_info{};String error;
 vapor::AtlasStream stream;PackedByteArray transfer;
 bool check(int32_t status){if(status==0){error="";return true;}uint8_t text[1024]{};vapor_last_error_v1(text,sizeof(text));error=String::utf8(reinterpret_cast<const char*>(text));if(error.is_empty())error="Vapor error "+String::num_int64(status);UtilityFunctions::push_error(error);return false;}
 bool id_ok(int64_t id){if(valid_id(id))return true;error="id must be uint32";return false;}
protected:
 static void _bind_methods(){
  ClassDB::bind_method(D_METHOD("configure","cells","cell_size","options"),&VaporSimulation::configure,DEFVAL(Dictionary()));
  ClassDB::bind_method(D_METHOD("close"),&VaporSimulation::close);
  ClassDB::bind_method(D_METHOD("reset"),&VaporSimulation::reset);
  ClassDB::bind_method(D_METHOD("advance","seconds"),&VaporSimulation::advance);
  ClassDB::bind_method(D_METHOD("step","count"),&VaporSimulation::step,DEFVAL(1));
  ClassDB::bind_method(D_METHOD("set_emitter","id","position","direction","options"),&VaporSimulation::set_emitter,DEFVAL(Dictionary()));
  ClassDB::bind_method(D_METHOD("remove_emitter","id"),&VaporSimulation::remove_emitter);
  ClassDB::bind_method(D_METHOD("set_capsule","id","a","b","radius","velocity"),&VaporSimulation::set_capsule,DEFVAL(Vector3()));
  ClassDB::bind_method(D_METHOD("set_box","id","minimum","maximum","velocity"),&VaporSimulation::set_box,DEFVAL(Vector3()));
  ClassDB::bind_method(D_METHOD("remove_obstacle","id"),&VaporSimulation::remove_obstacle);
  ClassDB::bind_method(D_METHOD("set_profile","id","rows","duration","start_time","repeat"),&VaporSimulation::set_profile,DEFVAL(0.0),DEFVAL(false));
  ClassDB::bind_method(D_METHOD("get_atlas_image"),&VaporSimulation::get_atlas_image);
  ClassDB::bind_method(D_METHOD("pump_atlas_image","request"),&VaporSimulation::pump_atlas_image,DEFVAL(true));
  ClassDB::bind_method(D_METHOD("get_field","field"),&VaporSimulation::get_field,DEFVAL(0));
  ClassDB::bind_method(D_METHOD("get_backend_info"),&VaporSimulation::get_backend_info);
  ClassDB::bind_method(D_METHOD("get_metrics"),&VaporSimulation::get_metrics);
  ClassDB::bind_method(D_METHOD("get_last_error"),&VaporSimulation::get_last_error);
 }
public:
 ~VaporSimulation(){close();}
 bool configure(Vector3i cells,double cell_size,const Dictionary& options){
  VaporConfig c{};if(!check(vapor_default_config_v1(&c,sizeof(c))))return false;
  if(cells.x<4||cells.y<4||cells.z<4){error="Each grid axis must be >=4";return false;}
  c.nx=cells.x;c.ny=cells.y;c.nz=cells.z;c.cell_size=cell_size;
  VaporBackendOptions backend{};backend.size=sizeof(backend);backend.version=1;backend.mode=VAPOR_CPU;backend.detail_scale=1;backend.detail_frequency=8;
  Array keys=options.keys();for(int i=0;i<keys.size();++i){String k=keys[i];Variant v=options[keys[i]];
   if(k=="backend"){String mode=v;if(mode=="cpu")backend.mode=VAPOR_CPU;else if(mode=="gpu")backend.mode=VAPOR_GPU;else if(mode=="hybrid")backend.mode=VAPOR_HYBRID;else if(mode=="auto")backend.mode=VAPOR_AUTO;else{error="Unknown backend";return false;}}
   else if(k=="detail_scale")backend.detail_scale=int64_t(v);
   else if(k=="detail_turbulence")backend.detail_turbulence=double(v);
   else if(k=="detail_frequency")backend.detail_frequency=double(v);
   else if(k=="allow_cpu_fallback"){if(bool(v))backend.flags|=VAPOR_ALLOW_CPU_FALLBACK;}
   else if(k=="allow_software_gpu"){if(bool(v))backend.flags|=VAPOR_ALLOW_SOFTWARE_GPU;}
   else if(k=="fixed_dt")c.fixed_dt=double(v);else if(k=="max_substeps")c.max_substeps=int64_t(v);
   else if(k=="pressure_iterations")c.pressure_iterations=int64_t(v);else if(k=="density_decay")c.density_decay=double(v);
   else if(k=="buoyancy")c.buoyancy=double(v);else if(k=="vorticity")c.vorticity=double(v);
   else if(k=="density_cap")c.density_cap=double(v);else if(k=="max_velocity")c.max_velocity=double(v);
   else if(k=="wind")xyz(c.wind,Vector3(v));else if(k=="origin")xyz(c.origin,Vector3(v));
   else if(k=="boundary")c.boundary=int64_t(v);else{error="Unknown option: "+k;return false;}}
  VaporHandle next=0;if(!check(vapor_create_ex_v1(&c,&backend,&next)))return false;
  VaporBackendInfo info{};if(!check(vapor_backend_info_v1(next,&info,sizeof(info)))){vapor_release_v1(next);return false;}
  close();handle=next;config=c;backend_info=info;return true;
 }
 void close(){stream.invalidate();transfer.clear();if(handle){vapor_release_v1(handle);handle=0;}}
 bool reset(){stream.invalidate();return check(vapor_reset_v1(handle));}
 bool step(int64_t count){return id_ok(count)&&check(vapor_step_v1(handle,uint32_t(count)));}
 Dictionary advance(double seconds){VaporAdvance a{};Dictionary out;if(!check(vapor_advance_v1(handle,seconds,&a,sizeof(a))))return out;out["steps"]=a.steps;out["alpha"]=a.alpha;out["dropped_seconds"]=a.dropped_seconds;out["simulated_seconds"]=a.simulated_seconds;return out;}
 bool set_emitter(int64_t id,Vector3 position,Vector3 direction,const Dictionary& options){if(!id_ok(id))return false;VaporEmitter e{};if(!check(vapor_default_emitter_v1(&e,sizeof(e))))return false;xyz(e.position,position);xyz(e.direction,direction);
  Array keys=options.keys();for(int i=0;i<keys.size();++i){String k=keys[i];Variant v=options[keys[i]];if(k=="radius")e.radius=double(v);else if(k=="length")e.length=double(v);else if(k=="speed")e.speed=double(v);else if(k=="density_rate")e.density_rate=double(v);else if(k=="temperature")e.temperature=double(v);else if(k=="enabled")e.enabled=bool(v)?1:0;else{error="Unknown emitter option: "+k;return false;}}
  return check(vapor_set_emitter_v1(handle,uint32_t(id),&e));}
 bool remove_emitter(int64_t id){return id_ok(id)&&check(vapor_remove_emitter_v1(handle,uint32_t(id)));}
 bool set_capsule(int64_t id,Vector3 a,Vector3 b,double radius,Vector3 velocity){if(!id_ok(id))return false;VaporObstacle o{};o.size=sizeof(o);o.version=1;o.kind=0;o.radius=radius;o.enabled=1;xyz(o.a,a);xyz(o.b,b);xyz(o.velocity,velocity);return check(vapor_set_obstacle_v1(handle,uint32_t(id),&o));}
 bool set_box(int64_t id,Vector3 a,Vector3 b,Vector3 velocity){if(!id_ok(id))return false;VaporObstacle o{};o.size=sizeof(o);o.version=1;o.kind=1;o.enabled=1;xyz(o.a,a);xyz(o.b,b);xyz(o.velocity,velocity);return check(vapor_set_obstacle_v1(handle,uint32_t(id),&o));}
 bool remove_obstacle(int64_t id){return id_ok(id)&&check(vapor_remove_obstacle_v1(handle,uint32_t(id)));}
 bool set_profile(int64_t id,const PackedFloat64Array& rows,double duration,double start_time,bool repeat){if(!id_ok(id)||rows.size()%4||rows.size()>256){error="Invalid profile rows";return false;}return check(vapor_set_profile_v1(handle,uint32_t(id),rows.ptr(),rows.size()/4,duration,start_time,repeat?1:0));}
 Ref<Image> get_atlas_image(){if(!handle)return {};PackedByteArray data;data.resize(int64_t(backend_info.render_cells[0])*backend_info.render_cells[1]*backend_info.render_cells[2]*4);if(!check(vapor_copy_atlas_v1(handle,data.ptrw(),data.size())))return {};return Image::create_from_data(backend_info.render_cells[0],backend_info.render_cells[1]*backend_info.render_cells[2],false,Image::FORMAT_RGBA8,data);}
 // Pump every rendered frame; request only at the chosen upload cadence. Null = no new image.
 Ref<Image> pump_atlas_image(bool request){
  if(!handle)return {};if(backend_info.active==VAPOR_CPU)return request?get_atlas_image():Ref<Image>();
  Ref<Image> image;const uint32_t n=backend_info.render_cells[0]*backend_info.render_cells[1]*backend_info.render_cells[2]*4;
  if(stream.pending()){
   if(transfer.size()!=n)transfer.resize(n);if(transfer.size()!=n){check(VAPOR_CAPACITY);return {};}
   bool ready=false;if(!check(stream.poll(handle,transfer.ptrw(),n,ready)))return {};
   if(ready)image=Image::create_from_data(backend_info.render_cells[0],backend_info.render_cells[1]*backend_info.render_cells[2],false,Image::FORMAT_RGBA8,transfer);
  }
  if(request&&!stream.pending())check(stream.request(handle));return image;
 }
 PackedFloat32Array get_field(int64_t field){PackedFloat32Array data;if(!id_ok(field))return data;uint32_t n=0;if(!check(vapor_field_len_v1(handle,uint32_t(field),&n)))return data;data.resize(n);if(!check(vapor_copy_field_v1(handle,uint32_t(field),data.ptrw(),n)))data.clear();return data;}
 Dictionary get_backend_info()const{Dictionary d;if(!handle)return d;d["requested"]=backend_info.requested;d["active"]=backend_info.active;d["detail_scale"]=backend_info.detail_scale;d["flags"]=backend_info.flags;d["render_cells"]=Vector3i(backend_info.render_cells[0],backend_info.render_cells[1],backend_info.render_cells[2]);d["gpu_bytes"]=int64_t(backend_info.gpu_bytes);d["hybrid_upload_bytes"]=int64_t(backend_info.hybrid_upload_bytes);return d;}
 Dictionary get_metrics(){VaporMetrics m{};Dictionary d;if(!check(vapor_metrics_v1(handle,&m,sizeof(m))))return d;d["ticks"]=int64_t(m.ticks);d["time"]=m.time;d["density_integral"]=m.density_integral;d["max_density"]=m.max_density;d["max_speed"]=m.max_speed;d["divergence_rms"]=m.divergence_rms;d["pressure_residual_rms"]=m.pressure_residual_rms;d["non_finite"]=m.non_finite;d["clamped_velocities"]=int64_t(m.clamped_velocities);d["cpu_bytes"]=int64_t(m.cpu_bytes);d["centroid"]=Vector3(m.centroid[0],m.centroid[1],m.centroid[2]);return d;}
 String get_last_error()const{return error;}
};
// Preset-based path. Procedural kinds have no simulation handle; report this explicitly.
class VaporEffect : public RefCounted {
 GDCLASS(VaporEffect,RefCounted);
 vapor::Effect fx;String error;vapor::AtlasStream stream;PackedByteArray transfer;
 bool check(int32_t status){if(!status){error="";return true;}uint8_t text[1024]{};vapor_last_error_v1(text,sizeof(text));error=String::utf8(reinterpret_cast<const char*>(text));if(error.is_empty())error="Vapor effect error "+String::num_int64(status);UtilityFunctions::push_error(error);return false;}
protected:
 static void _bind_methods(){
  ClassDB::bind_method(D_METHOD("create_effect","preset","quality","backend","detail_scale"),&VaporEffect::create_effect,DEFVAL(1),DEFVAL("cpu"),DEFVAL(1));
  ClassDB::bind_method(D_METHOD("play"),&VaporEffect::play);ClassDB::bind_method(D_METHOD("stop"),&VaporEffect::stop);ClassDB::bind_method(D_METHOD("reset"),&VaporEffect::reset);ClassDB::bind_method(D_METHOD("close"),&VaporEffect::close);
  ClassDB::bind_method(D_METHOD("advance","seconds"),&VaporEffect::advance);ClassDB::bind_method(D_METHOD("set_pose","position","direction"),&VaporEffect::set_pose);
  ClassDB::bind_method(D_METHOD("pump_atlas_image","request"),&VaporEffect::pump_atlas_image,DEFVAL(true));
  ClassDB::bind_method(D_METHOD("get_atlas_image"),&VaporEffect::get_atlas_image);ClassDB::bind_method(D_METHOD("get_definition"),&VaporEffect::get_definition);
 }
public:
 bool create_effect(int64_t id,int64_t quality,const String& backend,int64_t detail_scale){if(id<1||id>8||quality<0||quality>2||detail_scale<1||detail_scale>4)return check(VAPOR_INVALID);VaporBackendOptions o{};o.size=sizeof(o);o.version=1;o.detail_scale=uint32_t(detail_scale);o.detail_frequency=8;
 if(backend=="cpu")o.mode=VAPOR_CPU;else if(backend=="gpu")o.mode=VAPOR_GPU;else if(backend=="hybrid")o.mode=VAPOR_HYBRID;else if(backend=="auto")o.mode=VAPOR_AUTO;else return check(VAPOR_INVALID);const auto status=fx.create(uint32_t(id),uint32_t(quality),o);if(!status){stream.invalidate();transfer.clear();}return check(status);}
 bool play(){return check(fx.play());}bool stop(){return check(fx.stop());}bool reset(){stream.invalidate();return check(fx.reset());}void close(){stream.invalidate();transfer.clear();check(fx.close());}bool advance(double seconds){return check(fx.advance(seconds));}
 bool set_pose(Vector3 p,Vector3 d){float pos[3],dir[3];xyz(pos,p);xyz(dir,d);return check(fx.pose(pos,dir));}
 Ref<Image> get_atlas_image(){if(!fx.is_open())return {};auto& b=fx.backend();PackedByteArray data;data.resize(fx.atlas_bytes());if(!check(fx.atlas(data.ptrw(),data.size())))return {};return Image::create_from_data(b.render_cells[0],b.render_cells[1]*b.render_cells[2],false,Image::FORMAT_RGBA8,data);}
 Ref<Image> pump_atlas_image(bool request){
  if(!fx.is_open())return {};const auto& b=fx.backend();if(fx.is_procedural()||b.active==VAPOR_CPU)return request?get_atlas_image():Ref<Image>();
  Ref<Image> image;const uint32_t n=fx.atlas_bytes();
  if(stream.pending()){
   if(transfer.size()!=n)transfer.resize(n);if(transfer.size()!=n){check(VAPOR_CAPACITY);return {};}
   bool ready=false;if(!check(stream.poll(fx.handle(),transfer.ptrw(),n,ready)))return {};
   if(ready)image=Image::create_from_data(b.render_cells[0],b.render_cells[1]*b.render_cells[2],false,Image::FORMAT_RGBA8,transfer);
  }
  if(request&&!stream.pending())check(stream.request(fx.handle()));return image;
 }
 Dictionary get_definition(){Dictionary d;if(!fx.is_open())return d;auto& p=fx.definition();auto& b=fx.backend();d["kind"]=p.kind;d["active_backend"]=fx.is_procedural()?String("procedural-cpu"):(b.active==VAPOR_GPU?String("gpu"):b.active==VAPOR_HYBRID?String("hybrid"):String("cpu"));d["cells"]=Vector3i(p.config.nx,p.config.ny,p.config.nz);d["render_cells"]=Vector3i(b.render_cells[0],b.render_cells[1],b.render_cells[2]);d["extent"]=Vector3(p.config.nx*p.config.cell_size,p.config.ny*p.config.cell_size,p.config.nz*p.config.cell_size);d["density_cap"]=p.config.density_cap;d["extinction"]=p.material.extinction;d["colour"]=Vector3(p.material.colour[0],p.material.colour[1],p.material.colour[2]);d["anisotropy"]=p.material.anisotropy;d["albedo"]=p.material.albedo;d["ambient"]=p.material.ambient;d["emission"]=p.material.emission;d["thermal_fade"]=p.material.thermal_fade;d["ray_steps"]=p.ray_steps;d["upload_hz"]=p.upload_hz;d["time"]=fx.time();return d;}
};
void initialize_vapor(ModuleInitializationLevel level){if(level==MODULE_INITIALIZATION_LEVEL_SCENE){ClassDB::register_class<VaporSimulation>();ClassDB::register_class<VaporEffect>();}}
void terminate_vapor(ModuleInitializationLevel){}
extern "C" GDExtensionBool GDE_EXPORT vapor_godot_library_init(GDExtensionInterfaceGetProcAddress get_proc,GDExtensionClassLibraryPtr lib,GDExtensionInitialization* init){GDExtensionBinding::InitObject o(get_proc,lib,init);o.register_initializer(initialize_vapor);o.register_terminator(terminate_vapor);o.set_minimum_library_initialization_level(MODULE_INITIALIZATION_LEVEL_SCENE);return o.init();}
