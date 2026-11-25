#pragma once
// Data-only VPF1 decoder for C++17 hosts (Godot / Unreal / tools). No native SDK required.
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <limits>
#include <stdexcept>
#include <vector>
namespace vapor {
struct FieldAsset {
    std::array<std::uint32_t,3> cells{};
    std::array<double,3> extent{};
    double density_cap=0,time=0;
    std::vector<float> density,temperature;
    static constexpr std::size_t header=80,max_voxels=2097152;
    static FieldAsset decode(const std::uint8_t* b,std::size_t length) {
        static_assert(sizeof(float)==4 && sizeof(double)==8 && std::numeric_limits<float>::is_iec559 && std::numeric_limits<double>::is_iec559,"IEEE float required");
        if(!b||length<header||length>header+max_voxels*8)throw std::invalid_argument("invalid VPF length");
        auto u32=[&](std::size_t i){return std::uint32_t(b[i])|(std::uint32_t(b[i+1])<<8)|(std::uint32_t(b[i+2])<<16)|(std::uint32_t(b[i+3])<<24);};
        auto f64=[&](std::size_t i){std::uint64_t bits=std::uint64_t(u32(i))|(std::uint64_t(u32(i+4))<<32);double v;std::memcpy(&v,&bits,8);return v;};
        auto f32=[&](std::size_t i){auto bits=u32(i);float v;std::memcpy(&v,&bits,4);return v;};
        auto bounded=[](double x,double a,double z){return std::isfinite(x)&&x>=a&&x<=z;};
        if(u32(0)!=0x31465056u||u32(4)!=header||u32(20)||u32(68)||u32(76))throw std::invalid_argument("unsupported VPF header");
        FieldAsset out;std::size_t n=1;
        for(std::size_t i=0;i<3;++i){out.cells[i]=u32(8+4*i);out.extent[i]=f64(24+8*i);if(out.cells[i]<4||out.cells[i]>512||!bounded(out.extent[i],.0001,1e7))throw std::invalid_argument("invalid VPF grid");n*=out.cells[i];}
        out.density_cap=f64(48);out.time=f64(56);
        if(n>max_voxels||!bounded(out.density_cap,.00001,100)||!bounded(out.time,0,1e7)||u32(72)!=n*8||length!=header+n*8)throw std::invalid_argument("invalid VPF grid/payload");
        std::uint32_t crc=0xffffffffu;std::array<std::uint32_t,256> table{};
        for(std::size_t i=0;i<table.size();++i){auto c=static_cast<std::uint32_t>(i);for(int j=0;j<8;++j)c=(c>>1)^((c&1u)?0xedb88320u:0u);table[i]=c;}
        for(std::size_t i=header;i<length;++i){crc=(crc>>8)^table[(crc^b[i])&255u];}if((~crc)!=u32(64))throw std::invalid_argument("invalid VPF checksum");
        out.density.resize(n);out.temperature.resize(n);
        for(std::size_t i=0;i<n;++i){auto d=f32(header+i*4),t=f32(header+(n+i)*4);if(!bounded(d,0,out.density_cap*(1+1e-6))||!bounded(t,0,1e5))throw std::invalid_argument("invalid VPF scalar");out.density[i]=d;out.temperature[i]=t;}
        return out;
    }
    std::vector<float> interleaved_rg32f() const {
        if(density.size()!=temperature.size()||density.size()>max_voxels)throw std::invalid_argument("invalid field length");
        std::vector<float> out(density.size()*2);for(std::size_t i=0;i<density.size();++i){out[2*i]=density[i];out[2*i+1]=temperature[i];}return out;
    }
};
}
