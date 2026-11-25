#include "vapor_effect.hpp"
#include <type_traits>
static_assert(sizeof(VaporEffectPreset)==268);
static_assert(offsetof(VaporEffectPreset,config)==16);
static_assert(offsetof(VaporEffectPreset,emitter)==116);
static_assert(offsetof(VaporEffectPreset,material)==172);
static_assert(offsetof(VaporEffectPreset,procedural)==208);
static_assert(offsetof(VaporEffectPreset,duration)==264);
static_assert(!std::is_copy_constructible<vapor::Effect>::value);
static_assert(std::is_nothrow_move_constructible<vapor::Effect>::value);
int main(){vapor::Effect e;vapor::Effect f(std::move(e));return f.is_open();}
