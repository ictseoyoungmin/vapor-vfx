# Airborne smoke study

Independent Lab-only art-directed fictional VFX. The effect is not a physical explosion model. It does not calculate explosive forces, damage, fragmentation, or other real-world effects. No production defaults, Rust algorithms, or GPU compute shaders are changed.

`bake.py` creates artistic Float32 fields; `backdrop.py` creates the scene backdrop; `render.mjs` calls the existing `prepareFidelityVolume` JS CPU renderer; `scene.py` composites the fictional drone projection; `rebuild.py` is a portable CLI. `export_fields.py` writes selected fields using the public VPF1 data API. `inspect_audit.mjs` tests the actual inspector rendering API and lossless data contract. See the [example guide](../../examples/airborne-smoke/README.md).
