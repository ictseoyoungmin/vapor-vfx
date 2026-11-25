#include "vapor_field_sequence.hpp"
#include <fstream>
#include <iostream>
#include <iterator>
#include <cassert>
std::vector<uint8_t> read(const std::string& p,size_t max){std::ifstream f(p,std::ios::binary);if(!f)throw std::runtime_error("missing file");std::vector<uint8_t> b;for(char c;f.get(c);){if(b.size()>=max)throw std::runtime_error("oversize input");b.push_back(uint8_t(c));}return b;}
int main(int argc,char**argv){if(argc!=4)return 2;std::string dir=std::string(argv[1])+"/";auto idx=read(dir+"sequence.vpa",64+4096*16);vapor::FieldSequence s(idx.data(),idx.size(),[&](size_t i,size_t n){return read(dir+vapor::frame_filename(i),n);});auto a=s.sample(std::stod(argv[2]));auto raw=read(argv[3],80+2097152*8);auto b=vapor::FieldAsset::decode(raw.data(),raw.size());assert(a.cells==b.cells&&a.extent==b.extent&&a.time==b.time&&a.density.size()==b.density.size());assert(std::memcmp(a.density.data(),b.density.data(),a.density.size()*4)==0);assert(std::memcmp(a.temperature.data(),b.temperature.data(),a.temperature.size()*4)==0);std::cout<<"PASS exact Float32 bits for "<<a.density.size()<<" voxels in both channels\n";}
