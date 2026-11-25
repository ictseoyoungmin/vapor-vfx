#pragma once
#include "CoreMinimal.h"
#include "Components/SceneComponent.h"
#include "Engine/Texture2D.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "vapor_effect.hpp"
#include "vapor_atlas_stream.hpp"
#include "VaporVolumeComponent.generated.h"
/** Local unscaled domain. Unreal centimetres/Z-up -> core metres/Y-up.
 * Calls happen on the game thread; GPU/Hybrid atlas readbacks use polling. No RHI zero-copy bridge.
 */
UENUM(BlueprintType)
enum class EVaporBackend : uint8 {Auto=0,Cpu=1,Gpu=2,Hybrid=3};
UCLASS(ClassGroup=(Vapor),meta=(BlueprintSpawnableComponent))
class VAPORGAME_API UVaporVolumeComponent : public USceneComponent {
 GENERATED_BODY()
public:
 UVaporVolumeComponent();
 /** 0 keeps the legacy custom fluid configuration. 1..8 use the shared effect catalog. */
 UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="Vapor|Effect",meta=(ClampMin="0",ClampMax="8")) int32 PresetId=0;
 UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="Vapor|Effect",meta=(ClampMin="0",ClampMax="2")) int32 PresetQuality=1;
 UPROPERTY(VisibleAnywhere,BlueprintReadOnly,Category="Vapor|Effect") bool bProceduralCpu=false;
 UFUNCTION(BlueprintCallable,Category="Vapor|Effect") bool PlayEffect();
 UFUNCTION(BlueprintCallable,Category="Vapor|Effect") bool StopEffect();
 UFUNCTION(BlueprintCallable,Category="Vapor|Effect") bool SetEffectPoseWorld(FVector PositionCm,FVector Direction);
 UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="Vapor") FIntVector Cells=FIntVector(16,20,16);
 UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="Vapor",meta=(ClampMin="0.001")) float CellSizeMetres=.04f;
 UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="Vapor",meta=(ClampMin="1",ClampMax="60")) float UploadHz=20.f;
 UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="Vapor") EVaporBackend Backend=EVaporBackend::Cpu;
 UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="Vapor",meta=(ClampMin="1",ClampMax="4")) int32 DetailScale=1;
 UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="Vapor") bool bAllowCpuFallback=false;
 UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="Vapor") bool bAllowSoftwareGpu=false;
 UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="Vapor",meta=(ClampMin="0",ClampMax="2")) float DetailTurbulence=0;
 UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="Vapor",meta=(ClampMin="0.1",ClampMax="100")) float DetailFrequency=8;
 UPROPERTY(VisibleAnywhere,BlueprintReadOnly,Category="Vapor") EVaporBackend ActiveBackend=EVaporBackend::Cpu;
 UPROPERTY(VisibleAnywhere,BlueprintReadOnly,Category="Vapor") FIntVector RenderCells;
 UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="Vapor") bool bPaused=false;
 UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="Vapor") bool bSpawnDefaultEmitter=true;
 UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="Vapor") UMaterialInterface* VolumeMaterial=nullptr;
 UPROPERTY(VisibleAnywhere,BlueprintReadOnly,Category="Vapor") UTexture2D* DensityAtlas=nullptr;
 UPROPERTY(VisibleAnywhere,BlueprintReadOnly,Category="Vapor") FString LastError;
 UFUNCTION(BlueprintCallable,Category="Vapor") bool InitializeSimulation();
 UFUNCTION(BlueprintCallable,Category="Vapor") void ShutdownSimulation();
 UFUNCTION(BlueprintCallable,Category="Vapor") bool ResetSimulation();
 UFUNCTION(BlueprintCallable,Category="Vapor") bool SetEmitterWorld(int32 Id,FVector PositionCm,FVector Direction,float RadiusMetres=.025f,float SpeedMetresPerSecond=.6f,float DensityRate=20.f);
 UFUNCTION(BlueprintCallable,Category="Vapor") bool RemoveEmitter(int32 Id);
 UFUNCTION(BlueprintCallable,Category="Vapor") bool SetCapsuleWorld(int32 Id,FVector ACm,FVector BCm,float RadiusCm,FVector VelocityCmPerSecond);
 UFUNCTION(BlueprintCallable,Category="Vapor") bool RemoveObstacle(int32 Id);
 UFUNCTION(BlueprintCallable,Category="Vapor") bool BindMaterial(UMaterialInstanceDynamic* Material);
 UFUNCTION(BlueprintPure,Category="Vapor") FVector ToCoreMetres(FVector WorldCm) const;
 UFUNCTION(BlueprintPure,Category="Vapor") float GetDensityIntegral() const;
protected:
 void BeginPlay() override;
 void EndPlay(const EEndPlayReason::Type Reason) override;
 void TickComponent(float DeltaTime,ELevelTick TickType,FActorComponentTickFunction* ThisTickFunction) override;
private:
 uint32 Handle=0;double UploadElapsed=0;FIntVector ActiveCells;float ActiveCellSize=.04f;
 vapor::Effect PresetRuntime;
 vapor::AtlasStream AtlasTransfer;TArray<uint8> TransferPixels;
 uint32 ActiveHandle() const {return PresetRuntime.is_open()?PresetRuntime.handle():Handle;}
 bool IsRunning() const {return PresetRuntime.is_open()||Handle!=0;}
 float ActiveDensityCap=8.f;
 UPROPERTY(Transient) UMaterialInstanceDynamic* DynamicMaterial=nullptr;
 UPROPERTY(Transient) class UStaticMeshComponent* Proxy=nullptr;
 bool Check(int32 Status);
 bool PumpUpload(bool bRequest);
 bool QueuePixels(uint8* Data);
 bool ClearAtlas();
 bool UsesGpuAtlas() const{return ActiveBackend==EVaporBackend::Gpu||ActiveBackend==EVaporBackend::Hybrid;}
 void UpdateTransformParameters();
};
