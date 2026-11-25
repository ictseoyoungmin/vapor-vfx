# Vapor

**Cross-platform volumetric VFX · Experimental SDK & Fidelity Lab**

Create, render and exchange 3D density and temperature fields for game effects. Vapor separates the Rust runtime from independently executable research code. The project is a **research and source preview**, not a verified production game SDK.

![Actual CPU reference cloud render](site/media/cloud.png)

*Actual Fidelity Lab render; 176 × 88 × 120 Float32 grid. Native Rust / GPU image parity is not yet verified.*

## Explore

| Example | Execution path | Requirements |
| --- | --- | --- |
| [Airborne smoke](examples/airborne-smoke/index.html) | Pre-rendered V1/V2 film with comparison controls | Browser; open the standalone HTML |
| [Smoke volume inspector](examples/airborne-smoke/inspect.html) | Actual JS CPU rendering of saved Float32 fields | Local HTTP server + full assets |
| [Fidelity Lab](examples/high-fidelity/index.html) | Independent JS cloud/fog generation and optical rendering | Local HTTP server |
| [Animated cloud](examples/animated-cloud/index.html) | VPA1 keyframes + experimental WebGPU | WebGPU + full assets |
| [All examples](examples/index.html) | Reference and runtime demos | See each example |

From the repository root:

```sh
python -m http.server 8000 --bind 127.0.0.1
```

Open `http://localhost:8000/examples/`. The full SDK archive contains current VPF1/VPA1 assets; the lightweight source archive does not. Optional historic snapshots are not required for current cloud/fog or airborne film examples.

## Build the actual runtime

Python 3.11+, Rust 1.88+, Node 22 for web and reference checks; the target platform also needs its native linker and build tools. CPU-first:

```sh
python tools/validate_runtime.py --build --modes cpu --capture
python tools/validate_cloud_equivalence.py --profile hero --build
```

For WASM, GPU, Hybrid and host integrations, follow the [getting-started guide](docs/GETTING_STARTED_KO.md). The Python binding calls the compiled Rust C ABI. The independent Python/JS Lab is **not** a silent native fallback. Existing native and GPU execution is blocked/unverified in the delivery environment.

## Project map

- `crates/`, `shaders/`: Rust CPU, GPU and one-way Hybrid runtime sources.
- `bindings/`, `include/`, `adapters/`: Python, JS/TS, C#/C++, Unity, Godot and Unreal integrations.
- `lab/`: independent fluid/optics experiments and artistic VFX reproduction.
- `effects/`, `contracts/`, `fixtures/`: shared presets, data and validation contracts.
- `assets/`, `examples/`: reusable fields and demonstrations.
- `site/`: GitHub Pages templates and actual project-rendered media. `dist/pages/` is generated, not committed.

## Current status

| Component | Evidence |
| --- | --- |
| Cloud, fog and reference optics | Actual JS CPU results |
| VPF1/VPA1 data interchange | JS/Python/C++ executed; Rust/C# source readers |
| Airborne smoke | Film player and independent CPU field/optics tested |
| Rust CPU/WASM, WGSL GPU/Hybrid | Source implementation; runtime verification pending |
| Game engine adapters | Source integration; editor execution pending |

Distribution **0.24** is a documentation, example usability and website preparation revision. Rust core, ABI, bindings and Lab algorithms are unchanged from 0.23 (core 0.22.0; C ABI v1). See [work status](docs/WORK_STATUS_KO.md) and [milestones](docs/MILESTONES_KO.md). Test doubles and reference renders do not count as real Rust/WGSL execution.

## Documentation

| Document | Purpose |
| --- | --- |
| [Architecture](docs/ARCHITECTURE_KO.md) | Module ownership and dependencies |
| [Getting started](docs/GETTING_STARTED_KO.md) | Build and language/engine integration |
| [API contract](docs/API_CONTRACT_KO.md) | Data layout, runtime and lifecycle contracts |
| [Validation](docs/VALIDATION_KO.md) | Evidence, commands and acceptance criteria |
| [Milestones](docs/MILESTONES_KO.md) | Product goals and closure gates |
| [Work status](docs/WORK_STATUS_KO.md) | Current work and next decisions |
| [Research guide](lab/README.md) | Independent experiments |
| [Publishing guide](docs/PUBLISHING_KO.md) | GitHub Pages and redistribution checklist |
| [Contributing](CONTRIBUTING.md) | Development and review workflow |
| [Changelog](CHANGELOG.md) | Historical changes |

Build the standalone static website without a Rust compiler:

```sh
python tools/build_pages.py --assets auto
python -m http.server 8000 --bind 127.0.0.1 --directory dist/pages
```

**Rights:** no new open-source license has been assigned. Original notices are preserved in the optional history archive. Confirm source, asset and third-party redistribution rights before public hosting or release. The included Pages deployment workflow requires explicit manual acknowledgement; this package does not publish anything automatically.
