# Unity native desktop adapter — source integration, editor/build untested here

1. Run `python tools/build.py --native --gpu --stage-adapters` on the target OS.
2. Unity Package Manager → Add package from disk → select this directory's `package.json`.
3. Add `VaporVolume` to a GameObject with unit scale. It creates/disposes its own proxy cube, material and texture.
4. Assign `Vapor/VolumeBuiltIn` or `Vapor/VolumeURP` explicitly to avoid shader stripping. URP: enable the pipeline/camera **Depth Texture** option.
5. Set `emitterTransform`; its forward axis determines the jet. No transform means a default upward source. Call `SetCapsule` each frame for animated colliders.

Native DLL: `Runtime/Plugins/x86_64/vapor.dll` (Windows), `libvapor.so` (Linux), or macOS `.dylib`. Configure Plugin Importer for the matching OS/CPU. Source is shared with `bindings/dotnet/Vapor.Runtime/Vapor.cs`; do not also import that file into the same Unity assembly.

Select `backend` = Cpu, Gpu, Hybrid or Auto. Set `detailScale` for GPU detail. Native `--gpu` builds retain CPU mode; omit the flag for CPU-only. GPU/hybrid remains experimental and unexecuted here. Upload is RGBA8 and throttled by `uploadHz`; it is not zero-copy. The included materials support perspective cameras. Orthographic, XR/stereo, HDRP, consoles, mobile packaging, IL2CPP/AOT deployment and Unity WebGL are **not validated or supplied as finished integrations**. Direct browser support is the separate Rust WASM SDK, not this Unity plug-in. Turning off depth texture produces incorrect opaque-geometry occlusion.

Coordinates: Unity local positive box → Rust `[x,y,extent.z-z]`; directions/velocities `[x,y,-z]`. Root translation and rotation are permitted; root scale must stay one. Unit = metre. `Simulation` is synchronous; for larger grids, step it in a dedicated worker and only upload owned snapshots on the Unity main thread.

0.3: `sim.Backend` reports actual mode; `RenderVoxelCount` sizes atlas output, while `VoxelCount`/fields describe coarse physics. Native GPU atlas copies block and use a separate wgpu device, not the Unity graphics device.

0.8: `VaporVolume` and `VaporEffectVolume` use `AtlasUploadPump` for native GPU/Hybrid, with one pending readback ticket and the last complete texture retained until ready. CPU/procedural paths pack synchronously. `Texture.Apply`, compute submission, host copies and device/engine upload costs remain; no native GPU resource sharing or measured FPS improvement. Requires the 0.8 native library. Editor compile/run not verified.
