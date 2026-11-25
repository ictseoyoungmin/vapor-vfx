#include "vapor_atlas_stream.hpp"
#include <cassert>
#include <vector>
#include <cstdio>
// Real C++ helper against explicit C fixture, not a solver/backend test.
int main(){
 VaporConfig c{};assert(vapor_default_config_v1(&c,sizeof(c))==0);c.nx=c.ny=c.nz=4;
 VaporHandle h=0,other=0;assert(vapor_create_v1(&c,&h)==0);assert(vapor_create_v1(&c,&other)==0);
 vapor::AtlasStream s;assert(vapor_step_v1(h,9)==0);assert(s.request(h)==0&&s.pending()&&s.ticks()==9);
 assert(s.request(h)==0);assert(s.request(other)==VAPOR_HANDLE);
 bool ready=true;std::vector<uint8_t> data(4*4*4*4,77);
 assert(s.poll(h,data.data(),4,ready)==VAPOR_BUFFER&&!ready&&s.pending());
 assert(s.poll(other,data.data(),data.size(),ready)==VAPOR_HANDLE&&!ready);
 assert(vapor_step_v1(h,2)==0);assert(s.poll(h,data.data(),data.size(),ready)==0&&!ready&&s.pending());
 for(auto v:data)assert(v==77);
 assert(s.poll(h,data.data(),data.size(),ready)==0&&ready&&!s.pending()&&data[0]==9);
 assert(s.request(h)==0&&s.pending());assert(s.cancel()==0&&!s.pending());assert(s.cancel()==0);
 assert(s.request(h)==0&&s.pending());assert(vapor_reset_v1(h)==0);s.invalidate();assert(!s.pending());
 assert(s.request(h)==0&&s.ticks()==0);assert(s.cancel()==0);
 assert(vapor_release_v1(h)==0&&vapor_release_v1(other)==0);std::puts("PASS C++ AtlasStream lifecycle against C test double");
}
