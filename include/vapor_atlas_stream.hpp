#pragma once
#include "vapor.h"
namespace vapor {
// Borrowed-handle helper for engine game threads. Never owns or releases a simulation.
// The host must invalidate after reset/release; one consumer per handle.
class AtlasStream final {
    VaporAtlasTicket ticket_{};
    VaporHandle owner_=0;
public:
    AtlasStream()=default;
    AtlasStream(const AtlasStream&)=delete;
    AtlasStream& operator=(const AtlasStream&)=delete;
    bool pending()const noexcept{return ticket_.id!=0;}
    uint64_t ticks()const noexcept{return ticket_.ticks;}
    void invalidate() noexcept{ticket_={};owner_=0;}
    int32_t request(VaporHandle handle){
        if(!handle)return VAPOR_HANDLE;
        if(pending())return owner_==handle?VAPOR_OK:VAPOR_HANDLE;
        VaporAtlasTicket next{};const auto status=vapor_begin_atlas_v1(handle,&next,sizeof(next));
        if(!status&&next.id){ticket_=next;owner_=handle;}
        return status;
    }
    int32_t poll(VaporHandle handle,uint8_t* out,uint32_t bytes,bool& ready){
        ready=false;if(!pending())return VAPOR_OK;if(owner_!=handle)return VAPOR_HANDLE;
        uint32_t done=0;const auto status=vapor_poll_atlas_v1(handle,ticket_.id,out,bytes,&done);
        if(!status){ready=done!=0;if(ready)invalidate();}
        else if(status!=VAPOR_BUFFER&&status!=VAPOR_INVALID){invalidate();}
        return status;
    }
    int32_t cancel(){if(!pending())return VAPOR_OK;auto status=vapor_cancel_atlas_v1(owner_,ticket_.id);invalidate();return status;}
};
}
