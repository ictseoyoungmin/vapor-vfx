#include "vapor_field_asset.hpp"
#include <fstream>
#include <iterator>
#include <cassert>
#include <iostream>
int main(int argc,char** argv){assert(argc==2);std::ifstream f(argv[1],std::ios::binary);std::vector<std::uint8_t> b((std::istreambuf_iterator<char>(f)),{});auto a=vapor::FieldAsset::decode(b.data(),b.size());auto p=a.interleaved_rg32f();auto n=a.density.size();assert(p.size()==n*2);for(size_t i=0;i<n;i++){for(size_t c=0;c<2;c++){std::uint32_t v;std::memcpy(&v,&p[i*2+c],4);for(int k=0;k<4;k++)assert(((v>>(8*k))&255u)==b[80+4*(i+c*n)+k]);}}std::cout<<"PASS full exact decoded bits: "<<2*n<<" floats\n";}
