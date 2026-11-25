#pragma once
#include "vapor.h"
#include <cmath>
#include <utility>
// Native game-thread facade. Engine owns scene transforms and materials.
namespace vapor {
class Effect final {
    VaporHandle handle_=0;
    VaporEffectPreset definition_{};
    VaporBackendInfo backend_{};
    VaporEmitter source_{};
    double time_=0;
    bool playing_=false,open_=false;
public:
    Effect()=default;~Effect(){close();}
    Effect(const Effect&)=delete;Effect& operator=(const Effect&)=delete;
    Effect(Effect&& o) noexcept {swap(o);}
    Effect& operator=(Effect&& o) noexcept {if(this!=&o){close();swap(o);}return *this;}
    void swap(Effect& o) noexcept {using std::swap;swap(handle_,o.handle_);swap(definition_,o.definition_);swap(backend_,o.backend_);swap(source_,o.source_);swap(time_,o.time_);swap(playing_,o.playing_);swap(open_,o.open_);}
    bool is_open()const{return open_;}
    bool is_procedural()const{return open_&&definition_.kind!=0;}
    bool playing()const{return playing_;}
    double time()const{return time_;}
    VaporHandle handle()const{return handle_;} // borrowed, never release externally
    const VaporEffectPreset& definition()const{return definition_;}
    const VaporBackendInfo& backend()const{return backend_;}
    int32_t close(){auto h=handle_;handle_=0;time_=0;playing_=open_=false;return h?vapor_release_v1(h):VAPOR_OK;}
    int32_t create(uint32_t id,uint32_t quality,const VaporBackendOptions& options){
        Effect next;int32_t s=vapor_effect_preset_v1(id,quality,&next.definition_,sizeof(next.definition_));if(s)return s;
        next.source_=next.definition_.emitter;const auto& c=next.definition_.config;
        if(next.definition_.kind==0){s=vapor_create_ex_v1(&c,&options,&next.handle_);if(s)return s;s=vapor_backend_info_v1(next.handle_,&next.backend_,sizeof(next.backend_));if(s)return s;}
        else {if(options.mode!=VAPOR_CPU&&options.mode!=VAPOR_AUTO)return VAPOR_UNSUPPORTED;if(options.detail_scale!=1||options.detail_turbulence!=0)return VAPOR_UNSUPPORTED;
            next.backend_.size=sizeof(VaporBackendInfo);next.backend_.version=1;next.backend_.requested=options.mode;next.backend_.active=VAPOR_CPU;next.backend_.detail_scale=1;next.backend_.flags=VAPOR_COMPUTE_CPU;next.backend_.render_cells[0]=c.nx;next.backend_.render_cells[1]=c.ny;next.backend_.render_cells[2]=c.nz;}
        next.open_=true;swap(next);return VAPOR_OK;
    }
    int32_t play(){if(!open_)return VAPOR_HANDLE;
        if(handle_){double rows[256]{};uint32_t n=definition_.profile_count;if(n>64)return VAPOR_INVALID;int32_t s=vapor_effect_profile_v1(definition_.id,rows,256);if(s)return s;
            s=vapor_set_emitter_v1(handle_,0,&source_);if(s)return s;
            s=vapor_set_profile_v1(handle_,0,n?rows:nullptr,n,n?definition_.duration:2.,time_,0);if(s){vapor_remove_emitter_v1(handle_,0);playing_=false;return s;}}
        playing_=true;return VAPOR_OK;
    }
    int32_t stop(){if(!open_)return VAPOR_HANDLE;int32_t s=handle_?vapor_remove_emitter_v1(handle_,0):VAPOR_OK;if(!s)playing_=false;return s;}
    int32_t reset(){int32_t s=stop();if(s)return s;if(handle_&&(s=vapor_reset_v1(handle_)))return s;time_=0;return VAPOR_OK;}
    int32_t pose(const float position[3],const float direction[3]){if(!open_)return VAPOR_HANDLE;if(!handle_)return VAPOR_UNSUPPORTED;if(!position||!direction)return VAPOR_INVALID;
        VaporEmitter e=source_;double mag=0;for(int i=0;i<3;i++){if(!std::isfinite(position[i])||std::abs(position[i])>1e6||!std::isfinite(direction[i]))return VAPOR_INVALID;e.position[i]=position[i];e.direction[i]=direction[i];mag+=double(direction[i])*direction[i];}if(!std::isfinite(mag)||mag<1e-12||mag>1e30)return VAPOR_INVALID;
        if(playing_){int32_t s=vapor_set_emitter_v1(handle_,0,&e);if(s)return s;}source_=e;return VAPOR_OK;}
    int32_t advance(double seconds){if(!open_)return VAPOR_HANDLE;if(!std::isfinite(seconds)||seconds<0||seconds>10)return VAPOR_INVALID;
        if(handle_){VaporAdvance a{};int32_t s=vapor_advance_v1(handle_,seconds,&a,sizeof(a));if(s)return s;time_=a.simulated_seconds;}
        else if(playing_){if(time_+seconds>1e7)return VAPOR_INVALID;time_+=seconds;}
        return VAPOR_OK;}
    uint32_t atlas_bytes()const{return open_?backend_.render_cells[0]*backend_.render_cells[1]*backend_.render_cells[2]*4:0;}
    int32_t atlas(uint8_t* out,uint32_t bytes)const{if(!open_)return VAPOR_HANDLE;return handle_?vapor_copy_atlas_v1(handle_,out,bytes):vapor_procedural_atlas_v1(&definition_.config,&definition_.procedural,time_,out,bytes);}
};
}
