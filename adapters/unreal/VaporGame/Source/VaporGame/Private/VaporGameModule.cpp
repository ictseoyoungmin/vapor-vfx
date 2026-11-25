#include "Modules/ModuleManager.h"
#include "Interfaces/IPluginManager.h"
#include "Misc/Paths.h"
#include "ShaderCore.h"
class FVaporGameModule final : public IModuleInterface {
 public: void StartupModule() override {
  auto Plugin=IPluginManager::Get().FindPlugin(TEXT("VaporGame"));
  if(Plugin.IsValid())AddShaderSourceDirectoryMapping(TEXT("/Plugin/VaporGame"),FPaths::Combine(Plugin->GetBaseDir(),TEXT("Shaders")));
 }
};
IMPLEMENT_MODULE(FVaporGameModule,VaporGame)
