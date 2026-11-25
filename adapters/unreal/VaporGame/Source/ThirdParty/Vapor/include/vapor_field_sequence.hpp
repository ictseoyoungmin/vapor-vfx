#pragma once
// VPA1 data-only sequence API. Host loader must enforce requested byte count.
#include "vapor_field_asset.hpp"
#include <algorithm>
#include <deque>
#include <functional>
#include <string>
#include <utility>
namespace vapor {
inline uint32_t sequence_crc(const uint8_t* p,size_t n){uint32_t c=0xffffffffu;std::array<uint32_t,256> t{};for(size_t i=0;i<256;++i){auto v=uint32_t(i);for(int j=0;j<8;++j)v=(v>>1)^((v&1)?0xedb88320u:0u);t[i]=v;}for(size_t i=0;i<n;++i)c=(c>>8)^t[(c^p[i])&255u];return ~c;}
struct SequenceRecord{double time;uint32_t bytes,crc;};
inline std::string frame_filename(size_t i){if(i>=4096)throw std::invalid_argument("invalid frame index");auto s=std::to_string(i);return "frame_"+std::string(4-s.size(),'0')+s+".vpf";}
class FieldSequence {
    std::array<uint32_t,3> cells_{};std::array<double,3> extent_{};double cap_{};
    std::vector<SequenceRecord> records_;std::deque<std::pair<size_t,FieldAsset>> cache_;
    using Loader=std::function<std::vector<uint8_t>(size_t,size_t)>;
    Loader load_;
    void frame(size_t i){auto it=std::find_if(cache_.begin(),cache_.end(),[&](const auto& a){return a.first==i;});if(it!=cache_.end()){auto f=std::move(*it);cache_.erase(it);cache_.push_back(std::move(f));return;}
        const auto r=records_.at(i);auto raw=load_(i,r.bytes);if(raw.size()!=r.bytes||sequence_crc(raw.data(),raw.size())!=r.crc)throw std::invalid_argument("VPA frame checksum");auto f=FieldAsset::decode(raw.data(),raw.size());if(f.cells!=cells_||f.extent!=extent_||f.density_cap!=cap_||f.time!=r.time)throw std::invalid_argument("VPA frame metadata");if(cache_.size()==2)cache_.pop_front();cache_.emplace_back(i,std::move(f));}
    const FieldAsset& cached(size_t i)const{return std::find_if(cache_.begin(),cache_.end(),[&](const auto& a){return a.first==i;})->second;}
public:
    FieldSequence(const uint8_t* p,size_t length,Loader load):load_(std::move(load)){
        if(!p||!load_||length<80||length>64+4096*16)throw std::invalid_argument("VPA index length");
        auto u=[&](size_t o){return uint32_t(p[o])|(uint32_t(p[o+1])<<8)|(uint32_t(p[o+2])<<16)|(uint32_t(p[o+3])<<24);};
        auto d=[&](size_t o){uint64_t bits=uint64_t(u(o))|(uint64_t(u(o+4))<<32);double v;std::memcpy(&v,&bits,8);return v;};auto bound=[](double v,double a,double b){return std::isfinite(v)&&v>=a&&v<=b;};
        auto n=u(8);if(u(0)!=0x31415056u||u(4)!=64||n<1||n>4096||length!=64+n*16||u(28)||sequence_crc(p+16,length-16)!=u(12))throw std::invalid_argument("VPA index header/checksum");
        size_t voxels=1;for(size_t i=0;i<3;++i){cells_[i]=u(16+i*4);extent_[i]=d(32+i*8);if(!bound(cells_[i],4,512)||!bound(extent_[i],.0001,1e7))throw std::invalid_argument("VPA grid");voxels*=cells_[i];}cap_=d(56);if(voxels>2097152||!bound(cap_,.00001,100))throw std::invalid_argument("VPA grid");
        double prev=-1;for(size_t i=0;i<n;++i){size_t o=64+i*16;auto t=d(o);auto b=u(o+8);if(!bound(t,0,1e7)||t<=prev||b!=80+voxels*8)throw std::invalid_argument("VPA record");records_.push_back({t,b,u(o+12)});prev=t;}
    }
    const std::vector<SequenceRecord>& records()const{return records_;}size_t cached_frames()const{return cache_.size();}void clear(){cache_.clear();}
    FieldAsset sample(double time){if(!std::isfinite(time))throw std::invalid_argument("VPA sample time");time=std::clamp(time,records_.front().time,records_.back().time);auto i=size_t(std::upper_bound(records_.begin(),records_.end(),time,[](double t,const auto& r){return t<r.time;})-records_.begin()-1);frame(i);if(time==records_[i].time)return cached(i);frame(i+1);const auto& a=cached(i);const auto& b=cached(i+1);auto out=a;out.time=time;const double f=(time-a.time)/(b.time-a.time);for(size_t j=0;j<a.density.size();++j){out.density[j]=float(double(a.density[j])+(double(b.density[j])-double(a.density[j]))*f);out.temperature[j]=float(double(a.temperature[j])+(double(b.temperature[j])-double(a.temperature[j]))*f);}return out;}
};
}
