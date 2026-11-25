#include "vapor_field_sequence.hpp"
#include <fstream>
#include <iostream>
#include <iterator>
#include <cassert>
std::vector<uint8_t> read(const std::string& p){std::ifstream f(p,std::ios::binary);if(!f)throw std::runtime_error("missing file");return {std::istreambuf_iterator<char>(f),{}};}
int main(int argc,char** argv){if(argc!=2)return 2;std::string dir=std::string(argv[1])+"/";auto idx=read(dir+"sequence.vpa");size_t loads=0;vapor::FieldSequence s(idx.data(),idx.size(),[&](size_t i,size_t n){++loads;auto b=read(dir+vapor::frame_filename(i));assert(b.size()==n);return b;});auto actual=s.sample(.25);auto raw=read(dir+"sample-025.vpf");auto expected=vapor::FieldAsset::decode(raw.data(),raw.size());assert(actual.cells==expected.cells&&actual.extent==expected.extent&&actual.time==expected.time&&actual.density==expected.density&&actual.temperature==expected.temperature);assert(loads==2);actual.density[0]=99;assert(s.sample(.25).density==expected.density);assert(loads==2);assert(s.sample(999).time==s.records().back().time);assert(s.cached_frames()==2&&loads==3);idx[64]^=1;try{vapor::FieldSequence bad(idx.data(),idx.size(),[&](size_t,size_t){return raw;});return 1;}catch(const std::invalid_argument&){}std::cout<<"PASS C++ VPA golden fields, cache and CRC\n";}
