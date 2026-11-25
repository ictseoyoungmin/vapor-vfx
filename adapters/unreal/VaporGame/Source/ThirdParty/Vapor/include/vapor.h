#ifndef VAPOR_GAME_SDK_H
#define VAPOR_GAME_SDK_H
#include <stdint.h>
#include <stddef.h>
#if defined(_WIN32) && defined(VAPOR_LINK_SHARED)
# define VAPOR_API __declspec(dllimport)
#else
# define VAPOR_API
#endif
#ifdef __cplusplus
extern "C" {
#endif
#define VAPOR_ABI_VERSION 1u
typedef uint32_t VaporHandle;
enum VaporStatus { VAPOR_OK=0,VAPOR_INVALID=-1,VAPOR_HANDLE=-2,VAPOR_BUFFER=-3,VAPOR_CAPACITY=-4,VAPOR_NONFINITE=-5,VAPOR_INTERNAL=-6,VAPOR_BACKEND_UNAVAILABLE=-7,VAPOR_GPU_FAILURE=-8,VAPOR_UNSUPPORTED=-9 };
enum VaporField { VAPOR_DENSITY=0,VAPOR_TEMPERATURE=1,VAPOR_PRESSURE=2,VAPOR_SOLID=3,VAPOR_VELOCITY=4 };
enum VaporBoundary { VAPOR_OPEN=0,VAPOR_CLOSED=1 };
/* All coordinates are right-handed, Y-up, metres. Array storage is x-fastest. */
typedef struct VaporConfig {
 uint32_t size,version,nx,ny,nz;
 float cell_size,origin[3],fixed_dt;
 uint32_t max_substeps,pressure_iterations;
 float sor_omega,density_decay,cooling,buoyancy,density_weight,drag,vorticity,wind[3],max_velocity,density_cap;
 uint32_t boundary;
} VaporConfig;
typedef struct VaporEmitter {
 uint32_t size,version;float position[3],direction[3],radius,length,speed,density_rate,temperature;uint32_t enabled;
} VaporEmitter;
typedef struct VaporObstacle {
 uint32_t size,version,kind; /* 0=capsule (a==b => sphere), 1=AABB (a=min,b=max) */
 float a[3],b[3],radius,velocity[3];uint32_t enabled;
} VaporObstacle;
typedef struct VaporMetrics {
 uint32_t size,version;uint64_t ticks;double time,density_integral;
 float max_density,max_speed;double divergence_rms,pressure_residual_rms,centroid[3];
 uint32_t non_finite,reserved;uint64_t clamped_velocities;double dropped_seconds;uint64_t cpu_bytes;
} VaporMetrics;
typedef struct VaporAdvance {
 uint32_t size,version,steps,reserved;double alpha,dropped_seconds,simulated_seconds;
} VaporAdvance;
typedef struct VaporRender {
 uint32_t size,version,width,height,steps;
 float extinction,colour[3],eye[3],target[3],up[3],vertical_fov_degrees;
} VaporRender;

/* Additive v0.3 execution selection; old create_v1 remains CPU-only. */
enum VaporBackendMode { VAPOR_AUTO=0,VAPOR_CPU=1,VAPOR_GPU=2,VAPOR_HYBRID=3 };
enum VaporBackendOptionsFlags { VAPOR_ALLOW_CPU_FALLBACK=1,VAPOR_ALLOW_SOFTWARE_GPU=2 };
enum VaporBackendInfoFlags { VAPOR_COMPUTE_CPU=1,VAPOR_COMPUTE_GPU=2,VAPOR_ONE_WAY_HYBRID=4,
 VAPOR_INIT_FALLBACK=8,VAPOR_BLOCKING_READBACK=16,VAPOR_SOFTWARE_GPU=32,VAPOR_TICKETED_ATLAS=64 };
typedef struct VaporBackendOptions {
 uint32_t size,version,mode,detail_scale,flags,reserved;
 /* Fine kinematic curl amplitude (m/s; 0 disables), base wave number (rad/m). */
 float detail_turbulence,detail_frequency;
} VaporBackendOptions;
typedef struct VaporBackendInfo {
 uint32_t size,version,requested,active,detail_scale,flags,render_cells[3],reserved;
 uint64_t cpu_bytes,gpu_bytes,hybrid_upload_bytes;
} VaporBackendInfo;
VAPOR_API int32_t vapor_create_ex_v1(const VaporConfig* config,const VaporBackendOptions* backend,VaporHandle* out);
VAPOR_API int32_t vapor_backend_info_v1(VaporHandle handle,VaporBackendInfo* out,uint32_t out_size);
/* Padded MAC [nz+1,ny+1,nx+1,8], xyz velocities + reserved, density,temp,pressure,solid.
 * The caller must not substitute centred velocities here: hybrid needs the actual face field. */
VAPOR_API int32_t vapor_copy_mac_v1(VaporHandle handle,float* out,uint32_t elements);

/* v0.6 game effect catalog. Preset IDs stable; quality 0=low,1=medium,2=high.
 * Procedural kinds 1=cloud,2=fog (CPU-generated density atlas), 0=fluid. */
enum VaporEffectId { VAPOR_CIGARETTE_SMOKE=1,VAPOR_EXHALED_AEROSOL=2,VAPOR_CUMULUS_CLOUD=3,VAPOR_GROUND_FOG=4,VAPOR_STEAM=5,VAPOR_SMOKE=6,VAPOR_DUST=7,VAPOR_FLAME=8 };
typedef struct VaporEffectMaterial { float colour[3],extinction,anisotropy,albedo,emission,thermal_fade,ambient; } VaporEffectMaterial;
typedef struct VaporProcedural { uint32_t size,version,kind,seed;float coverage,humidity,erosion,wind[3]; } VaporProcedural;
typedef struct VaporEffectPreset { uint32_t size,version,id,kind;VaporConfig config;VaporEmitter emitter;VaporEffectMaterial material;VaporProcedural procedural;uint32_t ray_steps,upload_hz,ember,profile_count;float duration; } VaporEffectPreset;
VAPOR_API int32_t vapor_effect_preset_v1(uint32_t id,uint32_t quality,VaporEffectPreset* out,uint32_t bytes);
VAPOR_API int32_t vapor_effect_profile_v1(uint32_t id,double* out,uint32_t elements);
typedef struct VaporEmberVisual {float colour[3],intensity,heat,ash_fraction;} VaporEmberVisual;
VAPOR_API int32_t vapor_ember_visual_v1(double time,float progress,uint32_t lit,VaporEmberVisual* out,uint32_t bytes);
VAPOR_API int32_t vapor_procedural_atlas_v1(const VaporConfig* config,const VaporProcedural* settings,double time,uint8_t* out,uint32_t bytes);

/* Experimental Fidelity CPU v1. Local metres, x-fastest float32 fields.
 * Buffers must remain valid and output ranges must be mutually disjoint and disjoint from inputs.
 * Generation kind: 1=cloud, 2=fog, 3=dust (separate from legacy procedural kind).
 * Optional terrain: NULL,0 or nx*nz local heights. Optional scene: NULL,NULL,0 or
 * width*height depths (ray metres; 0=no occluder), and 3*width*height linear HDR floats.
 * Optional alpha: NULL,0 or width*height floats. All lengths are elements except rgba bytes.
 * Stateless convenience ABI: generator and optical cache rebuilt per call. */
typedef struct VaporFidelityGrid {uint32_t size,version,cells[3],reserved;double extent[3],density_cap;} VaporFidelityGrid;
typedef struct VaporFidelityDensity {uint32_t size,version,kind,seed;double coverage,humidity,erosion,wind[3];} VaporFidelityDensity;
typedef struct VaporFidelityOptics {uint32_t size,version,shadow_steps,reserved;double colour[3],extinction,anisotropy,albedo,emission,thermal_fade,ambient,direction[3],radiance[3],sky[3],ground[3],multi_scatter,light_scale;} VaporFidelityOptics;
typedef struct VaporFidelityCamera {uint32_t size,version,width,height,steps,dark;double eye[3],target[3],fov,exposure,jitter;} VaporFidelityCamera;
VAPOR_API int32_t vapor_fidelity_generate_v1(const VaporFidelityGrid*,const VaporFidelityDensity*,double,const float*,uint32_t,float*,float*,uint32_t);
VAPOR_API int32_t vapor_fidelity_render_v1(const VaporFidelityGrid*,const VaporFidelityOptics*,const VaporFidelityCamera*,const float*,const float*,uint32_t,const float*,const float*,uint32_t,uint8_t*,uint32_t,float*,uint32_t);


VAPOR_API uint32_t vapor_abi_version_v1(void);
VAPOR_API int32_t vapor_default_config_v1(VaporConfig* out,uint32_t out_size);
VAPOR_API int32_t vapor_default_emitter_v1(VaporEmitter* out,uint32_t out_size);
VAPOR_API int32_t vapor_create_v1(const VaporConfig* config,VaporHandle* out);
VAPOR_API int32_t vapor_release_v1(VaporHandle handle);
VAPOR_API int32_t vapor_reset_v1(VaporHandle handle);
VAPOR_API int32_t vapor_step_v1(VaporHandle handle,uint32_t steps);
VAPOR_API int32_t vapor_advance_v1(VaporHandle handle,double seconds,VaporAdvance* out,uint32_t out_size);
VAPOR_API int32_t vapor_set_emitter_v1(VaporHandle handle,uint32_t id,const VaporEmitter* emitter);
VAPOR_API int32_t vapor_remove_emitter_v1(VaporHandle handle,uint32_t id);
VAPOR_API int32_t vapor_set_obstacle_v1(VaporHandle handle,uint32_t id,const VaporObstacle* obstacle);
VAPOR_API int32_t vapor_remove_obstacle_v1(VaporHandle handle,uint32_t id);
/* rows=count control points [x01,speed_multiplier,amount01,density_multiplier]. count=0 clears. */
VAPOR_API int32_t vapor_set_profile_v1(VaporHandle handle,uint32_t id,const double* rows,uint32_t count,double duration,double start_time,uint32_t repeat);
VAPOR_API int32_t vapor_metrics_v1(VaporHandle handle,VaporMetrics* out,uint32_t out_size);
VAPOR_API int32_t vapor_field_len_v1(VaporHandle handle,uint32_t field,uint32_t* out);
VAPOR_API int32_t vapor_copy_field_v1(VaporHandle handle,uint32_t field,float* out,uint32_t elements);
/* v0.3: width=backend_info.render_cells[0], height=render_cells[1]*render_cells[2].
 * Base field/metrics remain at config.cells even in hybrid. Legacy CPU: width=nx,height=ny*nz; RGBA=(density/cap,temperature/16,solid,255). Linear UNORM, not sRGB. */
VAPOR_API int32_t vapor_copy_atlas_v1(VaporHandle handle,uint8_t* out,uint32_t bytes);
/* Additive v0.8: one outstanding snapshot per simulation. Snapshot tick is captured
 * at begin, not poll. VAPOR_OK + id=0 means BUSY; no request was submitted.
 * Poll writes ready=0 if pending, ready=1 if copied (ticket consumed). No output
 * bytes are changed on pending/error. BUFFER is retryable. Reset/cancel/release
 * invalidate tickets; IDs are scoped to the handle. No foreign pointer retained.
 * CPU packing is synchronous at begin. GPU/Hybrid submit then non-waiting poll.
 * The existing blocking copy remains valid and independent. Output and ready must not overlap.
 */
typedef struct VaporAtlasTicket { uint32_t size,version;uint64_t id,ticks;uint32_t bytes,reserved; } VaporAtlasTicket;
VAPOR_API int32_t vapor_begin_atlas_v1(VaporHandle handle,VaporAtlasTicket* out,uint32_t out_size);
VAPOR_API int32_t vapor_poll_atlas_v1(VaporHandle handle,uint64_t id,uint8_t* out,uint32_t bytes,uint32_t* ready);
VAPOR_API int32_t vapor_cancel_atlas_v1(VaporHandle handle,uint64_t id);
/* Premultiplied linear RGBA8; CPU preview renderer, NOT a game render-loop API. */
VAPOR_API int32_t vapor_render_v1(VaporHandle handle,const VaporRender* render,uint8_t* out,uint32_t bytes);
/* Last-error text belongs to calling OS thread; UTF-8 NUL-terminated when capacity>0. */
VAPOR_API uint32_t vapor_last_error_v1(uint8_t* out,uint32_t capacity);
/* WASM/FFI scratch allocation. Unknown/double frees return VAPOR_HANDLE. Max 64 MiB each. */
VAPOR_API void* vapor_alloc_v1(uint32_t bytes);
VAPOR_API int32_t vapor_free_v1(void* ptr);
#ifdef __cplusplus
}
static_assert(sizeof(VaporAtlasTicket)==32,"VaporAtlasTicket ABI");
static_assert(sizeof(VaporEmberVisual)==24,"VaporEmberVisual ABI");
static_assert(sizeof(VaporEffectMaterial)==36,"VaporEffectMaterial ABI");
static_assert(sizeof(VaporProcedural)==40,"VaporProcedural ABI");
static_assert(sizeof(VaporEffectPreset)==268,"VaporEffectPreset ABI");
static_assert(sizeof(VaporBackendOptions)==32,"VaporBackendOptions ABI");
static_assert(sizeof(VaporBackendInfo)==64,"VaporBackendInfo ABI");
static_assert(sizeof(VaporConfig)==100,"VaporConfig ABI");
static_assert(sizeof(VaporEmitter)==56,"VaporEmitter ABI");
static_assert(sizeof(VaporObstacle)==56,"VaporObstacle ABI");
static_assert(sizeof(VaporMetrics)==112,"VaporMetrics ABI");
static_assert(sizeof(VaporAdvance)==40,"VaporAdvance ABI");
static_assert(sizeof(VaporRender)==76,"VaporRender ABI");
#endif
/* Pointer contract: callers provide live, writable buffers of the advertised size;
 * no library can validate an arbitrary foreign address. No Rust-owned pointer escapes
 * except registered scratch buffers. Calls on one handle serialize; different handles
 * do not share simulation state. Release removes the token, while in-flight calls retain
 * an Arc until completion. Raw ABI release twice returns HANDLE; high-level close is idempotent.
 */
#endif
