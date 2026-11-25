# Airborne smoke V2 — game VFX example

This fictional visual study preserves the approved V1/V2 video streams. It is an artistic, unitless procedural smoke animation, not a physical blast, damage, or fluid simulation. No Rust solver or GPU runtime is used.

- `index.html`: standalone offline A/B player; play, seek, speed, repeat, zoom and frame-step controls. No internet or build required.
- `inspect.html`: real 3D VPF1 Float32 volume inspector, not a video; select one of three saved fields, orbit the camera, choose lighting, and render. The worker reuses prepared optical caches when only the camera changes. Uses the existing JS CPU Fidelity renderer, not Rust/WebGPU. Serve from the project root; requires included `assets/airborne-smoke/` (full package).
- `../../lab/airborne_smoke/`: portable source for the artistic field generation and V2 rendering recipe. All generated scratch data stay under `reports/local/` by default.
- `../../contracts/airborne-smoke.json`: scene/field/optical contract; coordinates are arbitrary game-scene units.

## Open
Double-click `index.html` for the offline player. For the inspector:

```sh
python -m http.server 8000 --bind 127.0.0.1
```

Open `http://localhost:8000/examples/airborne-smoke/inspect.html`. The three saved fields have 1,863,680 cells each. CPU rendering may take time; the viewer deliberately renders on demand instead of claiming interactive FPS. The viewer uses a sky background without the drone composite, so its image is not identical to the offline film.

## Reproduce
From the project root (Python + NumPy/SciPy/Pillow + Node):

```sh
python -m pip install -r lab/requirements.txt
python lab/airborne_smoke/rebuild.py --frame 56
python lab/airborne_smoke/export_fields.py --output assets/airborne-smoke
node lab/airborne_smoke/inspect_audit.mjs
```

The optional `--full` flag to `rebuild.py` regenerates the V2 film and requires FFmpeg; it uses a dedicated work directory and can generate hundreds of MB of scratch data. It does not modify the shipped standalone player. The 3.50 s single render was byte-compared with the archived V2 raw RGBA. Reproducing the old V1 film is outside this recipe; its original embedded video remains in the player. Cross-version dependency changes may affect pixel parity.
