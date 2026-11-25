# Unreal 5 native source plugin

This is a **source integration**: UHT/UnrealBuildTool, packaged-game loading and materials have not been run here. No precompiled plugin or `.uasset` is included. Desktop native targets only; no console, mobile or Web export claim.

## Build / component

Build the Rust dynamic library for the SAME target architecture and runtime as the game. From SDK root run `python tools/build.py --native --gpu --stage-adapters`. Copy this `VaporGame/` directory to your C++ project's `Plugins/`, regenerate project files, then build with your installed UE5 toolchain. Windows requires the MSVC Rust target, not MinGW. `VaporGame.Build.cs` deliberately fails rather than substituting a missing Rust library. macOS signing/rpaths and Linux packaged rpaths must be checked by the consuming project.

Add `VaporVolumeComponent` to an actor. Set `Cells`, `CellSizeMetres` before `BeginPlay`, keep world scale 1. The default emitter points core +Y (Unreal +Z). `SetEmitterWorld` and `SetCapsuleWorld` accept world positions in **centimetres**; emitter radius/speed use **metres** as named, capsule radius/velocity use centimetres. Core position = `(UE-local-Y,UE-local-Z,-UE-local-X)*0.01`. This is one explicit handedness conversion, not three separate tuning offsets. Rotation is supported. Runtime grid changes require `InitializeSimulation`.

`DensityAtlas` is a transient linear RGBA8 `Texture2D`, width RenderCells.X / height RenderCells.Y*RenderCells.Z. `BindMaterial(MID)` binds atlas/domain transform parameters. `SetEmitterWorld`, `RemoveEmitter`, `SetCapsuleWorld`, `RemoveObstacle`, `ResetSimulation`, `GetDensityIntegral` are Blueprint callable. The lower-level C ABI also exposes boxes, profiles and field export.

Uploads copy owned bytes and retire them in `UpdateTextureRegions`' cleanup callback; they never capture the destroyed component. Simulation runs on the game thread in this adapter. Tune a small grid and profiling budget before integration; no 60 FPS guarantee.

## Material setup (required, not an included compiled material)

Create a Surface / Unlit / Translucent material, **Two Sided**, with **Disable Depth Test** enabled. Use a `TwoSidedSign` mask so only back faces contribute (front faces opacity=0). Back-face proxy depth must not reject smoke in front of an opaque object; depth clipping belongs inside the march.

Add a Custom node with Output Type Float4 and Include File Path `/Plugin/VaporGame/VaporVolume.ush`. Inputs:

- `Atlas`: TextureObjectParameter `DensityAtlas` (the Custom node provides `AtlasSampler`).
- `EyeWorldCm`: CameraPositionWS. `SurfaceWorldCm`: AbsoluteWorldPosition.
- `OriginCm`, `AxisX`, `AxisY`, `AxisZ`: VectorParameters `VaporOriginCm`, `VaporAxisX`, `VaporAxisY`, `VaporAxisZ` (XYZ).
- `Grid`, `Extent`: VectorParameters `VaporGrid`, `VaporExtent` (XYZ).
- `Cap`: scalar `VaporDensityCap`=8. `Extinction`=5, `Colour`=(.78,.83,.9), `Steps`=72.
- `SceneDistanceCm`: **distance along this camera ray to opaque scene depth**, reconstructed from scene depth/world position in your material/render path. Raw nonlinear depth, SceneDepth eye-Z, and PixelDepth of the proxy are NOT this distance. For a standalone empty-scene smoke preview use a large constant such as 1e8; opaque geometry will then not occlude the volume.

Custom code:

```hlsl
return VaporRaymarch(Atlas, AtlasSampler, EyeWorldCm, SurfaceWorldCm,
 OriginCm, AxisX, AxisY, AxisZ, Grid, Extent, Cap, Extinction, Colour, Steps, SceneDistanceCm);
```

Connect XYZ to Emissive and W times the back-face mask to Opacity. Assign this material to `VolumeMaterial` on the component; it creates/scales the box proxy and a MID. Alternatively bind your own MID and proxy explicitly. Perspective cameras only. Overlapping volumes, orthographic/XR, transparent-depth sorting, Niagara integration and automatic scene-depth reconstruction are not part of this source adapter.

0.3: select `Backend` (Cpu/Gpu/Hybrid/Auto), `DetailScale`, and optional initial fallback/software GPU flags before initialization. `ActiveBackend` reports the actual mode. GPU uses a separate wgpu device. 0.8 component atlas transfer uses one ticket and polls readiness before queuing the texture upload; no native UE RHI sharing. Legacy diagnostic readback still blocks. `GetDensityIntegral` also incurs a coarse GPU readback in GPU-only mode.
