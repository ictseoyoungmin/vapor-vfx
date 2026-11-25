using UnrealBuildTool;
using System.IO;
public class VaporGame : ModuleRules {
 public VaporGame(ReadOnlyTargetRules Target):base(Target){
  PCHUsage=PCHUsageMode.UseExplicitOrSharedPCHs;
  PublicDependencyModuleNames.AddRange(new[]{"Core","CoreUObject","Engine"});
  PrivateDependencyModuleNames.AddRange(new[]{"Projects","RenderCore","RHI"});
  string Root=Path.GetFullPath(Path.Combine(ModuleDirectory,"../ThirdParty/Vapor"));
  PublicIncludePaths.Add(Path.Combine(Root,"include"));
  string Bin=Path.Combine(PluginDirectory,"Binaries","ThirdParty");
  if(Target.Platform==UnrealTargetPlatform.Win64){
   PublicAdditionalLibraries.Add(Path.Combine(Root,"Win64","vapor.dll.lib"));
   PublicDelayLoadDLLs.Add("vapor.dll");
   RuntimeDependencies.Add("$(TargetOutputDir)/vapor.dll",Path.Combine(Bin,"Win64","vapor.dll"));
  }else if(Target.Platform==UnrealTargetPlatform.Linux){
   PublicAdditionalLibraries.Add(Path.Combine(Bin,"Linux","libvapor.so"));
   RuntimeDependencies.Add(Path.Combine(Bin,"Linux","libvapor.so"));
   PublicRuntimeLibraryPaths.Add(Path.Combine(Bin,"Linux"));
  }else if(Target.Platform==UnrealTargetPlatform.Mac){
   PublicAdditionalLibraries.Add(Path.Combine(Bin,"Mac","libvapor.dylib"));
   RuntimeDependencies.Add(Path.Combine(Bin,"Mac","libvapor.dylib"));
  }else throw new BuildException("Vapor source adapter currently stages desktop native targets only.");
 }
}
