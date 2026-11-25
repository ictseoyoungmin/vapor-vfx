/* TEST DOUBLE ONLY. Not a solver, not a runtime, never distributed in dist/.
 * Compile both host and WASM to validate ABI marshalling/lifetimes independently
 * of Rust compilation. All field/atlas values are deliberate sentinel data. */
#include "vapor.h"
#ifndef __wasm__
#include <stdlib.h>
#endif
static void zero(void* p,uint32_t n){uint8_t* x=p;while(n--)*x++=0;}
static char error_text[]="fixture rejected request";
typedef struct Slot {VaporHandle h;VaporConfig config;uint64_t ticks;VaporEmitter emitter;VaporObstacle obstacle;uint32_t requested,fallback;uint64_t atlas_id,atlas_next,atlas_ticks;uint32_t atlas_pending;} Slot;
static Slot slots[64];static uint32_t next_id=1;
static Slot* slot(VaporHandle h){for(int i=0;i<64;i++)if(slots[i].h==h&&h)return &slots[i];return 0;}
uint32_t vapor_abi_version_v1(void){return 1;}
int32_t vapor_default_config_v1(VaporConfig* c,uint32_t n){if(!c||n<sizeof(*c))return -3;zero(c,sizeof(*c));c->size=sizeof(*c);c->version=1;c->nx=8;c->ny=10;c->nz=8;c->cell_size=.04f;c->fixed_dt=1.f/60;c->max_substeps=4;c->pressure_iterations=24;c->density_cap=8;c->max_velocity=12;return 0;}
int32_t vapor_default_emitter_v1(VaporEmitter* e,uint32_t n){if(!e||n<sizeof(*e))return -3;zero(e,sizeof(*e));e->size=sizeof(*e);e->version=1;e->direction[1]=1;e->radius=.04f;e->length=.08f;e->enabled=1;return 0;}
int32_t vapor_create_v1(const VaporConfig* c,VaporHandle* h){if(!h)return -1;*h=0;if(!c||c->size!=100||c->version!=1||c->nx<4||c->ny<4||c->nz<4||c->nx>192||c->ny>192||c->nz>192)return -1;for(int i=0;i<64;i++)if(!slots[i].h){slots[i].h=next_id++;slots[i].config=*c;slots[i].ticks=0;slots[i].requested=1;slots[i].fallback=0;slots[i].atlas_id=0;slots[i].atlas_next=1;slots[i].atlas_pending=0;*h=slots[i].h;return 0;}return -4;}
int32_t vapor_release_v1(VaporHandle h){Slot* s=slot(h);if(!s)return -2;s->h=0;return 0;}
int32_t vapor_reset_v1(VaporHandle h){Slot* s=slot(h);if(!s)return -2;s->ticks=0;s->atlas_id=0;s->atlas_pending=0;return 0;}
int32_t vapor_step_v1(VaporHandle h,uint32_t n){Slot* s=slot(h);if(!s)return -2;if(n>600)return -1;s->ticks+=n;return 0;}
int32_t vapor_advance_v1(VaporHandle h,double dt,VaporAdvance* a,uint32_t n){Slot* s=slot(h);if(!s)return -2;if(!a||n<sizeof(*a))return -3;if(!(dt>=0&&dt<=3600))return -1;zero(a,sizeof(*a));a->size=sizeof(*a);a->version=1;a->steps=dt>0?1:0;a->alpha=.25;a->dropped_seconds=.5;a->simulated_seconds=s->config.fixed_dt*a->steps;s->ticks+=a->steps;return 0;}
int32_t vapor_set_emitter_v1(VaporHandle h,uint32_t id,const VaporEmitter* e){Slot* s=slot(h);if(!s)return -2;if(!e||e->size!=56||e->version!=1||id>=32)return -1;s->emitter=*e;return 0;}
int32_t vapor_remove_emitter_v1(VaporHandle h,uint32_t id){return !slot(h)?-2:id>=32?-1:0;}
int32_t vapor_set_obstacle_v1(VaporHandle h,uint32_t id,const VaporObstacle* o){Slot* s=slot(h);if(!s)return -2;if(!o||o->size!=56||o->version!=1||id>=32)return -1;s->obstacle=*o;return 0;}
int32_t vapor_remove_obstacle_v1(VaporHandle h,uint32_t id){return vapor_remove_emitter_v1(h,id);}
int32_t vapor_set_profile_v1(VaporHandle h,uint32_t id,const double* rows,uint32_t count,double duration,double start,uint32_t repeat){(void)rows;(void)duration;(void)start;(void)repeat;if(!slot(h))return -2;return id>=32||(count!=0&&(count<2||count>64))?-1:0;}
int32_t vapor_metrics_v1(VaporHandle h,VaporMetrics* m,uint32_t n){Slot* s=slot(h);if(!s)return -2;if(!m||n<sizeof(*m))return -3;zero(m,sizeof(*m));m->size=sizeof(*m);m->version=1;m->ticks=s->ticks;m->time=s->ticks*(double)s->config.fixed_dt;m->density_integral=1.25;m->max_density=s->emitter.density_rate;m->max_speed=s->emitter.speed;m->centroid[0]=s->emitter.position[0];m->centroid[1]=s->emitter.position[1];m->centroid[2]=s->emitter.position[2];m->pressure_residual_rms=s->obstacle.radius;m->cpu_bytes=1234567;m->clamped_velocities=17;return 0;}
int32_t vapor_field_len_v1(VaporHandle h,uint32_t f,uint32_t* out){Slot* s=slot(h);if(!s)return -2;if(f>4||!out)return -1;*out=s->config.nx*s->config.ny*s->config.nz*(f==4?3:1);return 0;}
int32_t vapor_copy_field_v1(VaporHandle h,uint32_t f,float* out,uint32_t count){uint32_t n=0;int r=vapor_field_len_v1(h,f,&n);if(r)return r;if(!out||count<n)return -3;for(uint32_t i=0;i<n;i++)out[i]=(float)(i%97)+f*.125f;return 0;}
int32_t vapor_copy_atlas_v1(VaporHandle h,uint8_t* out,uint32_t count){uint32_t n=0;int r=vapor_field_len_v1(h,0,&n);if(r)return r;if(!out||count<n*4)return -3;for(uint32_t i=0;i<n;i++){out[i*4]=(uint8_t)(i%251);out[i*4+1]=9;out[i*4+2]=3;out[i*4+3]=255;}return 0;}
/* Ticketed ABI test double; one artificial pending poll. Encodes submission tick in R[0]. */
int32_t vapor_begin_atlas_v1(VaporHandle h,VaporAtlasTicket* out,uint32_t size){Slot* s=slot(h);if(!s)return -2;if(!out||size<sizeof(*out))return -3;zero(out,sizeof(*out));out->size=sizeof(*out);out->version=1;if(s->atlas_id)return 0;s->atlas_id=s->atlas_next++;s->atlas_ticks=s->ticks;s->atlas_pending=1;out->id=s->atlas_id;out->ticks=s->atlas_ticks;out->bytes=s->config.nx*s->config.ny*s->config.nz*4;return 0;}
int32_t vapor_poll_atlas_v1(VaporHandle h,uint64_t id,uint8_t* out,uint32_t bytes,uint32_t* ready){Slot* s=slot(h);if(!s)return -2;if(!ready||!out)return -1;*ready=0;if(!id||id!=s->atlas_id)return -2;uint32_t n=s->config.nx*s->config.ny*s->config.nz*4;if(bytes<n)return -3;if(s->atlas_pending){s->atlas_pending=0;return 0;}int32_t result=vapor_copy_atlas_v1(h,out,bytes);if(result)return result;out[0]=(uint8_t)(s->atlas_ticks%251);s->atlas_id=0;*ready=1;return 0;}
int32_t vapor_cancel_atlas_v1(VaporHandle h,uint64_t id){Slot* s=slot(h);if(!s||!id||id!=s->atlas_id)return -2;s->atlas_id=0;s->atlas_pending=0;return 0;}
int32_t vapor_render_v1(VaporHandle h,const VaporRender* r,uint8_t* out,uint32_t n){if(!slot(h))return -2;if(!r||r->size!=76||r->version!=1)return -1;uint32_t count=r->width*r->height*4;if(!out||n<count)return -3;zero(out,count);return 0;}
uint32_t vapor_last_error_v1(uint8_t* out,uint32_t capacity){uint32_t n=sizeof(error_text)-1;if(out&&capacity){uint32_t m=n<capacity-1?n:capacity-1;for(uint32_t i=0;i<m;i++)out[i]=error_text[i];out[m]=0;}return n;}
/* Extended ABI TEST DOUBLE: GPU and hybrid ALWAYS report unavailable. */
static uint32_t backend_words[8];
uint32_t vapor_test_backend_word(uint32_t i){return i<8?backend_words[i]:0;}
int32_t vapor_create_ex_v1(const VaporConfig* c,const VaporBackendOptions* o,VaporHandle* h){
 if(h)*h=0;
 if(!o||!h||o->size!=sizeof(*o)||o->version!=1||o->reserved||o->mode>3||o->detail_scale<1||o->detail_scale>4||(o->flags&~3u))return -1;
 const uint8_t* bytes=(const uint8_t*)o;
 for(uint32_t i=0;i<8;i++){backend_words[i]=0;for(uint32_t b=0;b<4;b++)backend_words[i]|=(uint32_t)bytes[i*4+b]<<(8*b);}
 if(o->mode==VAPOR_GPU||o->mode==VAPOR_HYBRID||(o->mode==VAPOR_AUTO&&!(o->flags&VAPOR_ALLOW_CPU_FALLBACK)))return VAPOR_BACKEND_UNAVAILABLE;
 if(o->mode==VAPOR_CPU&&(o->detail_scale!=1||o->detail_turbulence!=0))return -1;
 int32_t r=vapor_create_v1(c,h);if(r)return r;Slot* s=slot(*h);s->requested=o->mode;s->fallback=o->mode==VAPOR_AUTO;return 0;
}
int32_t vapor_backend_info_v1(VaporHandle h,VaporBackendInfo* out,uint32_t bytes){
 Slot* s=slot(h);if(!s)return -2;if(!out||bytes<sizeof(*out))return -3;
 zero(out,sizeof(*out));out->size=sizeof(*out);out->version=1;out->requested=s->requested;out->active=VAPOR_CPU;out->detail_scale=1;
 out->flags=VAPOR_COMPUTE_CPU|(s->fallback?VAPOR_INIT_FALLBACK:0);out->render_cells[0]=s->config.nx;out->render_cells[1]=s->config.ny;out->render_cells[2]=s->config.nz;out->cpu_bytes=1234567;return 0;
}
int32_t vapor_copy_mac_v1(VaporHandle h,float* out,uint32_t elements){
 Slot* s=slot(h);if(!s)return -2;uint32_t n=(s->config.nx+1)*(s->config.ny+1)*(s->config.nz+1)*8;
 if(!out||elements<n){return -3;}for(uint32_t i=0;i<n;i++)out[i]=(float)(i%8);return 0;
}
#ifdef __wasm__
void* memcpy(void* dst,const void* src,size_t n){uint8_t* d=dst;const uint8_t* s=src;for(size_t i=0;i<n;i++)d[i]=s[i];return dst;}
extern unsigned char __heap_base;
static uintptr_t cursor=0;
static uintptr_t allocated[1024];
void* vapor_alloc_v1(uint32_t bytes){if(!bytes||bytes>64*1024*1024)return 0;if(!cursor)cursor=((uintptr_t)&__heap_base+7)&~(uintptr_t)7;int k=-1;for(int i=0;i<1024;i++)if(!allocated[i]){k=i;break;}if(k<0)return 0;uintptr_t p=cursor;cursor=(cursor+bytes+7)&~(uintptr_t)7;size_t pages=(cursor+65535)/65536;size_t old=__builtin_wasm_memory_size(0);if(pages>old&&__builtin_wasm_memory_grow(0,pages-old)==(size_t)-1)return 0;allocated[k]=p;zero((void*)p,bytes);return (void*)p;}
int32_t vapor_free_v1(void* p){for(int i=0;i<1024;i++)if(allocated[i]==(uintptr_t)p&&p){allocated[i]=0;return 0;}return -2;}
#else
void* vapor_alloc_v1(uint32_t bytes){return calloc(1,bytes);}
int32_t vapor_free_v1(void* p){free(p);return 0;}
#endif
/* Fidelity ABI SENTINELS only. These values intentionally do not represent a volume. */
int32_t vapor_fidelity_generate_v1(const VaporFidelityGrid* g,const VaporFidelityDensity* s,double time,const float* terrain,uint32_t tc,float* density,float* temperature,uint32_t n){
 if(!g||!s||g->size!=sizeof(*g)||s->size!=sizeof(*s)||g->version!=1||s->version!=1||g->reserved||s->kind<1||s->kind>3||n!=g->cells[0]*g->cells[1]*g->cells[2]||!density||!temperature)return -1;
 if(tc!=(terrain?g->cells[0]*g->cells[2]:0))return -1;
 for(uint32_t i=0;i<n;i++){density[i]=(float)(s->coverage+time+g->extent[0]);temperature[i]=(float)(s->seed+s->wind[2]+(tc?terrain[0]:0)+10*s->kind);}return 0;
}
int32_t vapor_fidelity_render_v1(const VaporFidelityGrid* g,const VaporFidelityOptics* o,const VaporFidelityCamera* c,const float* density,const float* temperature,uint32_t n,const float* depth,const float* radiance,uint32_t sc,uint8_t* rgba,uint32_t bytes,float* alpha,uint32_t ac){
 if(!g||!o||!c||g->size!=sizeof(*g)||o->size!=sizeof(*o)||c->size!=sizeof(*c)||g->version!=1||o->version!=1||c->version!=1||g->reserved||o->reserved)return -1;
 uint32_t p=c->width*c->height;if(n!=g->cells[0]*g->cells[1]*g->cells[2]||!density||!temperature||bytes!=p*4||ac!=p||!rgba||!alpha||sc!=(depth&&radiance?p:0))return -1;
 for(uint32_t i=0;i<p;i++){rgba[4*i]=(uint8_t)o->shadow_steps;rgba[4*i+1]=(uint8_t)c->steps;rgba[4*i+2]=(uint8_t)(sc?depth[0]:0);rgba[4*i+3]=255;alpha[i]=density[0]+temperature[0]+(float)(o->extinction+c->eye[0]+(sc?radiance[0]:0));}return 0;
}
