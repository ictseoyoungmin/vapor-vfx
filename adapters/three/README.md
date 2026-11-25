# Three.js adapter (source)

Pass the caller's THREE module to `createVaporVolume`. The adapter owns only its Mesh, geometry, material and linear atlas texture; `dispose()` releases those resources, not the host renderer/camera. Worker owns the simulation and must be disposed separately.

`update(Uint8Array)` uploads an owned RGBA8 snapshot. `setSceneDepth(texture,width,height)` accepts a separate opaque scene depth texture, standard WebGL clip-depth, and its physical pixel dimensions. A back-face proxy is used and hardware depth test is disabled; without the explicit depth texture opaque objects will not correctly occlude smoke. Do not sample the same depth attachment that is currently being written.

Perspective cameras only. No logarithmic/reversed depth, TAA history, XR, multi-volume sorting or zero-copy interop. Shader colour and premultiplied alpha output must be integrated with the host's linear/render-target colour pipeline. GPU compilation and screenshots have not been verified in this environment.
