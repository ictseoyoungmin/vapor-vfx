# Godot 4 native adapter — source, engine execution not tested

Rust C ABI → godot-cpp GDExtension → GDScript. Godot .NET can alternatively use `bindings/dotnet`.

1. In the SDK root: `python tools/build.py --native --gpu --stage-adapters`.
2. Obtain **godot-cpp matching the target Godot editor** separately. It is not bundled.
3. `cmake -S adapters/godot -B build/godot -DGODOT_CPP_DIR=/absolute/path/to/godot-cpp -DCMAKE_BUILD_TYPE=Release`
4. `cmake --build build/godot --config Release`
5. Open `adapters/godot/project/project.godot` with Godot 4.4+ of the corresponding ABI. Binaries are placed in `project/bin/`.

The sample uses a perspective camera, metre units, right-handed Y-up coordinates identical to the core. For a transformed volume, convert world positions and velocities into its local unscaled metre coordinates. All calls from the supplied GDScript facade are on the main thread. Large CPU grids will block it; do not treat the example as a production frame-budget guarantee.

`configure(cells,cell_size,options)`, `advance(seconds)`, `step(count)`, `reset()`, `close()`, `set_emitter`, `set_capsule` (a=b is a sphere), `set_box`, `remove_obstacle`, `set_profile`, `get_field`, `get_metrics`, `get_atlas_image` are exposed. Emitter replacement is a full update, not a patch of the previous emitter. Configure creates the replacement first, so an invalid configuration preserves the existing simulation.

The atlas is linear RGBA8, no mipmaps. The shader clips against opaque scene depth, supports the Godot 4 compatibility vs Vulkan NDC distinction, and performs a limited self-shadow march. Transparent-surface ordering, overlapping smoke domains, XR and orthographic cameras are not solved. This package does not claim GDExtension Web export: use the direct browser WASM adapter for the web target.

No `.so`, `.dll`, `.dylib` or godot-cpp checkout is included. The GDExtension and shader have not been compiled/run in an actual Godot editor in this environment.

0.3: configure options include `backend` (cpu/gpu/hybrid/auto), `detail_scale`, `allow_cpu_fallback`, `allow_software_gpu`, `detail_turbulence`, `detail_frequency`. `get_backend_info()` reports the actual mode and `render_cells`. Atlas images use the fine dimensions; physical extent and fields remain coarse. Legacy `get_atlas_image()` may block. In 0.8 `pump_atlas_image(request)` polls the pending GPU/Hybrid ticket and returns a new image only when ready; examples retain the previous texture. When resetting from custom scripts clear the displayed texture if needed. Not RenderingDevice zero-copy.
