#include "VaporVolumeComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "vapor.h"
namespace {
void Put(float* P,FVector V){P[0]=float(V.X);P[1]=float(V.Y);P[2]=float(V.Z);}
FVector MapDirection(FVector Local){return FVector(Local.Y,Local.Z,-Local.X);}
}
UVaporVolumeComponent::UVaporVolumeComponent(){PrimaryComponentTick.bCanEverTick=true;}
bool UVaporVolumeComponent::Check(int32 S){if(S==0){LastError.Reset();return true;}uint8 Text[1024]{};vapor_last_error_v1(Text,sizeof(Text));LastError=UTF8_TO_TCHAR(reinterpret_cast<const char*>(Text));if(LastError.IsEmpty())LastError=FString::Printf(TEXT("Vapor error %d"),S);UE_LOG(LogTemp,Warning,TEXT("%s"),*LastError);return false;}
void UVaporVolumeComponent::BeginPlay(){Super::BeginPlay();InitializeSimulation();}
void UVaporVolumeComponent::EndPlay(const EEndPlayReason::Type Reason){ShutdownSimulation();Super::EndPlay(Reason);}
FVector UVaporVolumeComponent::ToCoreMetres(FVector WorldCm)const{return MapDirection(GetComponentTransform().InverseTransformPositionNoScale(WorldCm))*.01;}
bool UVaporVolumeComponent::InitializeSimulation(){
 if(!GetComponentTransform().GetScale3D().Equals(FVector::OneVector,.0001)){LastError=TEXT("Vapor domain requires unit world scale; use CellSizeMetres.");return false;}
 VaporConfig C{};VaporBackendOptions Options{};Options.size=sizeof(Options);Options.version=1;Options.mode=uint32(Backend);Options.detail_scale=uint32(DetailScale);
 Options.flags=(bAllowCpuFallback?VAPOR_ALLOW_CPU_FALLBACK:0)|(bAllowSoftwareGpu?VAPOR_ALLOW_SOFTWARE_GPU:0);Options.detail_turbulence=DetailTurbulence;Options.detail_frequency=DetailFrequency;
 uint32 Next=0;VaporBackendInfo Info{};vapor::Effect NewEffect;
 if(PresetId!=0){
  if(PresetId<1||PresetId>8||PresetQuality<0||PresetQuality>2){LastError=TEXT("Invalid Vapor preset/quality");return false;}
  if(!Check(NewEffect.create(uint32(PresetId),uint32(PresetQuality),Options)))return false;
  C=NewEffect.definition().config;Info=NewEffect.backend();
  if(bSpawnDefaultEmitter&&!Check(NewEffect.play()))return false;
 }else{
  if(Cells.X<4||Cells.Y<4||Cells.Z<4){LastError=TEXT("Invalid cell dimensions");return false;}
  if(!Check(vapor_default_config_v1(&C,sizeof(C))))return false;
  C.nx=Cells.X;C.ny=Cells.Y;C.nz=Cells.Z;C.cell_size=CellSizeMetres;C.pressure_iterations=24;
  if(!Check(vapor_create_ex_v1(&C,&Options,&Next)))return false;
  if(!Check(vapor_backend_info_v1(Next,&Info,sizeof(Info)))){vapor_release_v1(Next);return false;}
  if(bSpawnDefaultEmitter){VaporEmitter E{};vapor_default_emitter_v1(&E,sizeof(E));E.position[0]=C.nx*C.cell_size*.5f;E.position[1]=C.cell_size*2.5f;E.position[2]=C.nz*C.cell_size*.5f;E.direction[0]=0;E.direction[1]=1;E.direction[2]=0;E.speed=.6f;E.density_rate=20;if(!Check(vapor_set_emitter_v1(Next,0,&E))){vapor_release_v1(Next);return false;}}
 }
 FIntVector Fine(Info.render_cells[0],Info.render_cells[1],Info.render_cells[2]);
 if(Fine.X>16384||int64(Fine.Y)*Fine.Z>16384){if(Next)vapor_release_v1(Next);LastError=TEXT("Atlas exceeds desktop texture budget");return false;}
 UTexture2D* Tex=UTexture2D::CreateTransient(Fine.X,Fine.Y*Fine.Z,PF_R8G8B8A8);
 if(!Tex){if(Next)vapor_release_v1(Next);LastError=TEXT("Cannot allocate density atlas");return false;}
 Tex->SRGB=false;Tex->Filter=TF_Bilinear;Tex->AddressX=TA_Clamp;Tex->AddressY=TA_Clamp;Tex->NeverStream=true;Tex->UpdateResource();
 ShutdownSimulation();Handle=Next;PresetRuntime=std::move(NewEffect);bProceduralCpu=PresetRuntime.is_procedural();DensityAtlas=Tex;ActiveCells=FIntVector(C.nx,C.ny,C.nz);RenderCells=Fine;ActiveBackend=static_cast<EVaporBackend>(Info.active);ActiveCellSize=C.cell_size;ActiveDensityCap=C.density_cap;
 if(VolumeMaterial){
  Proxy=NewObject<UStaticMeshComponent>(GetOwner());Proxy->SetupAttachment(this);Proxy->SetStaticMesh(LoadObject<UStaticMesh>(nullptr,TEXT("/Engine/BasicShapes/Cube.Cube")));Proxy->SetCollisionEnabled(ECollisionEnabled::NoCollision);Proxy->SetCastShadow(false);Proxy->RegisterComponent();
  FVector Ext(ActiveCells.Z*ActiveCellSize,ActiveCells.X*ActiveCellSize,ActiveCells.Y*ActiveCellSize);
  Proxy->SetRelativeLocation(FVector(-Ext.X,Ext.Y,Ext.Z)*50);Proxy->SetRelativeScale3D(Ext);
  DynamicMaterial=UMaterialInstanceDynamic::Create(VolumeMaterial,this);Proxy->SetMaterial(0,DynamicMaterial);BindMaterial(DynamicMaterial);
 }
 if((UsesGpuAtlas()&&!ClearAtlas())||!PumpUpload(true)){ShutdownSimulation();return false;}return true;
}
void UVaporVolumeComponent::ShutdownSimulation(){AtlasTransfer.invalidate();TransferPixels.Empty();PresetRuntime.close();bProceduralCpu=false;if(Handle){vapor_release_v1(Handle);Handle=0;}if(Proxy){Proxy->DestroyComponent();Proxy=nullptr;}DensityAtlas=nullptr;DynamicMaterial=nullptr;UploadElapsed=0;}
bool UVaporVolumeComponent::ResetSimulation(){
 const auto Status=PresetRuntime.is_open()?PresetRuntime.reset():vapor_reset_v1(Handle);AtlasTransfer.invalidate();
 return Check(Status)&&(!UsesGpuAtlas()||ClearAtlas())&&PumpUpload(true);
}
bool UVaporVolumeComponent::PlayEffect(){return Check(PresetRuntime.play());}
bool UVaporVolumeComponent::StopEffect(){return Check(PresetRuntime.stop());}
bool UVaporVolumeComponent::SetEffectPoseWorld(FVector PositionCm,FVector Direction){float P[3],D[3];Put(P,ToCoreMetres(PositionCm));Put(D,MapDirection(GetComponentTransform().InverseTransformVectorNoScale(Direction)));return Check(PresetRuntime.pose(P,D));}
bool UVaporVolumeComponent::SetEmitterWorld(int32 Id,FVector PositionCm,FVector Direction,float Radius,float Speed,float Rate){if(PresetRuntime.is_open()&&Id==0){LastError=TEXT("Use SetEffectPoseWorld for preset source slot 0");return false;}if(Id<0){LastError=TEXT("Id must be nonnegative");return false;}VaporEmitter E{};vapor_default_emitter_v1(&E,sizeof(E));Put(E.position,ToCoreMetres(PositionCm));Put(E.direction,MapDirection(GetComponentTransform().InverseTransformVectorNoScale(Direction)));E.radius=Radius;E.speed=Speed;E.density_rate=Rate;return Check(vapor_set_emitter_v1(ActiveHandle(),uint32(Id),&E));}
bool UVaporVolumeComponent::RemoveEmitter(int32 Id){return Id>=0&&Check(PresetRuntime.is_open()&&Id==0?PresetRuntime.stop():vapor_remove_emitter_v1(ActiveHandle(),uint32(Id)));}
bool UVaporVolumeComponent::SetCapsuleWorld(int32 Id,FVector A,FVector B,float RadiusCm,FVector VelocityCm){if(Id<0)return false;VaporObstacle O{};O.size=sizeof(O);O.version=1;O.kind=0;O.enabled=1;Put(O.a,ToCoreMetres(A));Put(O.b,ToCoreMetres(B));Put(O.velocity,MapDirection(GetComponentTransform().InverseTransformVectorNoScale(VelocityCm))*.01);O.radius=RadiusCm*.01f;return Check(vapor_set_obstacle_v1(ActiveHandle(),uint32(Id),&O));}
bool UVaporVolumeComponent::RemoveObstacle(int32 Id){return Id>=0&&Check(vapor_remove_obstacle_v1(ActiveHandle(),uint32(Id)));}
bool UVaporVolumeComponent::BindMaterial(UMaterialInstanceDynamic* M){if(!M||!DensityAtlas)return false;DynamicMaterial=M;M->SetTextureParameterValue(TEXT("DensityAtlas"),DensityAtlas);M->SetVectorParameterValue(TEXT("VaporGrid"),FLinearColor(RenderCells.X,RenderCells.Y,RenderCells.Z,0));M->SetVectorParameterValue(TEXT("VaporExtent"),FLinearColor(ActiveCells.X*ActiveCellSize,ActiveCells.Y*ActiveCellSize,ActiveCells.Z*ActiveCellSize,0));M->SetScalarParameterValue(TEXT("VaporDensityCap"),ActiveDensityCap);if(PresetRuntime.is_open()){const auto& P=PresetRuntime.definition();const auto& O=P.material;M->SetVectorParameterValue(TEXT("VaporColour"),FLinearColor(O.colour[0],O.colour[1],O.colour[2],1));M->SetScalarParameterValue(TEXT("VaporExtinction"),O.extinction);M->SetScalarParameterValue(TEXT("VaporSteps"),P.ray_steps);M->SetScalarParameterValue(TEXT("VaporAnisotropy"),O.anisotropy);M->SetScalarParameterValue(TEXT("VaporAlbedo"),O.albedo);M->SetScalarParameterValue(TEXT("VaporAmbient"),O.ambient);M->SetScalarParameterValue(TEXT("VaporEmission"),O.emission);M->SetScalarParameterValue(TEXT("VaporThermalFade"),O.thermal_fade);}UpdateTransformParameters();return true;}
void UVaporVolumeComponent::UpdateTransformParameters(){if(!DynamicMaterial)return;const FTransform T=GetComponentTransform();auto Param=[&](const TCHAR* Name,FVector V){DynamicMaterial->SetVectorParameterValue(Name,FLinearColor(V.X,V.Y,V.Z,0));};Param(TEXT("VaporOriginCm"),T.GetLocation());Param(TEXT("VaporAxisX"),T.GetUnitAxis(EAxis::X));Param(TEXT("VaporAxisY"),T.GetUnitAxis(EAxis::Y));Param(TEXT("VaporAxisZ"),T.GetUnitAxis(EAxis::Z));}
bool UVaporVolumeComponent::QueuePixels(uint8* Data){if(!DensityAtlas){delete[] Data;return false;}auto* Region=new FUpdateTextureRegion2D(0,0,0,0,RenderCells.X,RenderCells.Y*RenderCells.Z);
 // Render-thread upload owns both allocations until cleanup; never capture this.
 DensityAtlas->UpdateTextureRegions(0,1,Region,RenderCells.X*4,4,Data,[](uint8* D,const FUpdateTextureRegion2D* R){delete[] D;delete R;});return true;}
bool UVaporVolumeComponent::ClearAtlas(){if(!DensityAtlas)return false;const uint32 Size=uint32(RenderCells.X)*RenderCells.Y*RenderCells.Z*4;return QueuePixels(new uint8[Size]());}
bool UVaporVolumeComponent::PumpUpload(bool bRequest){
 if(!DensityAtlas||!IsRunning())return false;
 const uint32 Size=uint32(RenderCells.X)*RenderCells.Y*RenderCells.Z*4;
 if(!UsesGpuAtlas()){
  if(!bRequest)return true;
  uint8* Data=new uint8[Size];if(!Check(PresetRuntime.is_open()?PresetRuntime.atlas(Data,Size):vapor_copy_atlas_v1(Handle,Data,Size))){delete[] Data;return false;}return QueuePixels(Data);
 }
 if(AtlasTransfer.pending()){
  if(TransferPixels.Num()!=int32(Size))TransferPixels.SetNumUninitialized(Size);
  bool Ready=false;if(!Check(AtlasTransfer.poll(ActiveHandle(),TransferPixels.GetData(),Size,Ready)))return false;
  if(Ready){uint8* Data=new uint8[Size];FMemory::Memcpy(Data,TransferPixels.GetData(),Size);if(!QueuePixels(Data))return false;}
 }
 return !bRequest||AtlasTransfer.pending()||Check(AtlasTransfer.request(ActiveHandle()));
}
void UVaporVolumeComponent::TickComponent(float Dt,ELevelTick Type,FActorComponentTickFunction* Tick){
 Super::TickComponent(Dt,Type,Tick);if(!IsRunning())return;
 if(bPaused){if(AtlasTransfer.pending())PumpUpload(false);return;}
 VaporAdvance A{};if(!Check(PresetRuntime.is_open()?PresetRuntime.advance(Dt):vapor_advance_v1(Handle,Dt,&A,sizeof(A)))){bPaused=true;return;}
 UpdateTransformParameters();UploadElapsed+=Dt;const double Period=1.0/FMath::Clamp(PresetRuntime.is_open()?float(PresetRuntime.definition().upload_hz):UploadHz,1.f,60.f);const bool Request=UploadElapsed>=Period;
 if(Request)UploadElapsed=FMath::Fmod(UploadElapsed,Period);if(!PumpUpload(Request))bPaused=true;
}
float UVaporVolumeComponent::GetDensityIntegral()const{VaporMetrics M{};return vapor_metrics_v1(ActiveHandle(),&M,sizeof(M))==0?float(M.density_integral):0;}
