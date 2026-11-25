#include "vapor_field_asset.hpp"
#include <cassert>
#include <fstream>
#include <iterator>
int main(int argc,char**argv){assert(argc==2);std::ifstream f(argv[1],std::ios::binary);std::vector<std::uint8_t> bytes((std::istreambuf_iterator<char>(f)),{});auto field=vapor::FieldAsset::decode(bytes.data(),bytes.size());assert(field.cells[0]==4&&field.cells[1]==5&&field.cells[2]==6);assert(field.extent[2]==3&&field.time==1.25&&field.density[3]==3.0f/128);auto packed=field.interleaved_rg32f();assert(packed.size()==240&&packed[6]==3.0f/128&&packed[7]==3.0f/16);for(int i:{0,4,8,20,64,68,72,76,80}){auto corrupted=bytes;corrupted[i]^=255;bool rejected=false;try{vapor::FieldAsset::decode(corrupted.data(),corrupted.size());}catch(const std::invalid_argument&){rejected=true;}assert(rejected);}return 0;}
