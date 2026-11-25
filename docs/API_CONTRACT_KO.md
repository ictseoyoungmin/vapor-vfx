# API·공통 필드 계약
정본: `include/vapor.h`, `include/vapor_effect.hpp`, `include/vapor_atlas_stream.hpp`, Rust FFI, JS 타입, `effects/presets.json`.

| 계약 | 내용 |
|---|---|
| 좌표 | 로컬 미터; x-fastest (`x + nx*(y+ny*z)`) |
| 물리 | MAC staggered faces, 고정 dt, substep 상한 |
| 실행 모드 | 요청/실제 모드 조회; 명시 허용 없는 CPU fallback 금지 |
| Hybrid | CPU coarse MAC → GPU fine scalar 단방향; feedback 없음 |
| Atlas | RGBA8 linear UNORM, width=renderNx, height=renderNy×renderNz; R=density/cap, G=temperature/16, B=solid, A=255 |
| Atlas ticket | 최대 1개 outstanding; begin tick; pending 출력 불변; reset/cancel/release 무효화 |
| Native Fidelity | Float32 density/temperature, metric extent 및 cap; 별도 version=1 ABI 구조체 |
| Scene depth | ray distance metres, 0=occluder 없음; scene linear HDR RGB |
| Fidelity RGBA | tone-mapped display RGBA8(A=255), volume alpha 별도 Float32; 기존 `vapor_render_v1` linear premultiplied와 다름 |

구름·안개·먼지만 Fidelity 생성. 유체는 실제 solver field 전달. terrain은 안개/먼지의 nx×nz 높이. 최대 2,097,152복셀, 화면 축 1~1600, steps 8~512, pixel×steps ≤180M. 외부 버퍼는 호출 동안 유효하고 서로 겹치지 않아야 한다.

Python/C# `FidelityCPU` 및 JS `NativeFidelityCPU`는 실제 Rust ABI만 사용. JS `generateFidelityVolume`/`prepareFidelityVolume`은 독립 CPU 구현. `GpuFidelityVolumeRenderer`는 별도 WebGPU 구현. 실제 실행 없이 동등성 또는 프레임 성능을 주장하지 않는다.

## M2 후보: Rust 직접 API (기본 경로 아님)

`Simulation::new_conservative_density(Config)`는 기존 MAC 속도·압력·온도 계산을 유지하고, 밀도만 MUSCL/SSP-RK2 및 정규화된 물리 원통 분출원으로 처리한다. `density_budget()`은 마지막 완료 스텝의 `DensityBudget`을 제공하며 `reset()` 또는 snapshot import 후 None이다. 기존 `Simulation::new`는 변경하지 않는다.

밀도×m³ 단위의 before, injected, boundary_outflow, decayed, saturated, after, residual과 CFL substeps를 기록한다. kg 단위 실제 액적 질량은 아니다. 추가 메모리는 밀도 복셀당 Float64 네 개(32B)와 분출 quadrature의 고정 크기 스택이다. 내부 장애물과 잘린 활성 분출원은 지원하지 않으며 오류를 반환한다. 원래 운동량·열원은 격자 확대 모델 유지. C ABI / Python / JS / .NET 및 GPU/Hybrid에는 이 후보를 노출하지 않는다.

### M2 국소 플룸 후보 (실제 Rust 실행 미검증)
- `Simulation::new_converged_density(Config)`는 기존 분출 속도/열 및 보존 밀도 수송을 유지하되 열린 도메인 CG를 사용한다.
- `Simulation::new_resolved_plume(Config, ResolvedPlumeOptions)`는 위 경로에 원통 물리 support의 MAC face/열 cell quadrature를 추가한다. `seed_amplitude=0..0.1`, `seed_frequency_hz=0..50`, 기본 0. 길이/직경은 각각 2/4셀 이상. 효과별 base speed에서 frequency를 선택한 실험일 뿐 물리적으로 보정된 난류 모델은 아니다.
- `pressure_report()`는 최근 압력 해법의 iterations, initial divergence RMS, f32 저장 후 residual RMS 및 실제 투영된 velocity divergence RMS(투영 전에는 None)를 제공한다. Reset/import 시 None. 실패한 step에도 실패 원인 진단이 남을 수 있다. CG workspace는 복셀당 32B, 기존 conservative workspace 32B에 추가된다. 잔차 실패 시 step 오류 및 reset 필요. 압력 잔차와 실제 투영 후 divergence를 구분하고, 두 게이트나 속도 clamp 기준이 실패하면 step 오류로 처리한다.
- 내부 장애물, closed domain, AMR/near-far 결합, ABI/GPU/Hybrid 노출 미지원. 기존 API 동작 유지.

## Float32 GPU field source
`GpuFieldVolume.create(device, volume, {origin})` takes `cells`, `extent`, `densityCap`, `fields.density`/`temperature` as x-fastest Float32Arrays. Packed vec4=(density,temperature,0,0). Capacity 2,097,152 voxels and device binding limits enforced. Source owns only its buffer. `replace` is asynchronous, one in flight, commits a new epoch only after validation; failure preserves previous field unless disposed. `setOrigin` changes local-to-world translation only; no new density or light cache invalidation. Source is not a fluid solver and sourceModel is informational, not provenance proof. `renderSource()` is borrowed and valid until replacement/disposal; dispose renderer first. Actual WebGPU execution pending.

## VPF1 baked Float32 interchange
Data-only snapshot. Little endian, planar Float32 x-fastest index `x + nx*(y+ny*z)`; density plane then temperature plane. No quantization, no executable content, no embedded rendering settings. `contracts/cloud-hero.json` and sidecar JSON specify scene/material; VPF alone cannot guarantee a rendered appearance. Coordinates/extent follow the existing right-handed field contract.

| Offset (bytes) | Encoding / meaning |
|---|---|
| 0, 4 | `VPF1`, u32 header length 80 |
| 8–19, 20 | u32 nx,ny,nz; flags zero |
| 24–47 | f64 extent x,y,z |
| 48, 56 | f64 density cap, time |
| 64, 68, 72, 76 | u32 payload CRC32, zero, payload size, zero |
| 80 onwards | two contiguous Float32 planes, exact 8*n bytes |

Each dimension 4–512, total ≤ 2,097,152, extent 0.0001–1e7, cap 0.00001–100, time 0–1e7. Finite scalars, nonnegative density ≤ cap*(1+1e-6), temperature ≤ 1e5. Reject unknown flags/reserved, invalid sizes, CRC mismatch, nonfinite/out-of-range values. CRC detects accidental payload corruption, NOT authenticity; sidecar SHA-256 covers entire file.

Rust `field_asset::BakedField::{encode,decode}`, Python `vapor_game.field_asset`, JS `encodeFieldAsset/decodeFieldAsset`, C# `FieldAsset.Decode`, C++17 `vapor::FieldAsset::decode`. C ABI v1 unchanged. Native renderer accepts decoded fields through existing Fidelity API. Unity `VaporBakedVolume` uploads RGFloat; Godot/Unreal host reader provided, not editor integration. Rust/C# and GPU execution not verified.

## VPA1 animated field index

A directory contains `sequence.vpa` and independently validated `frame_0000.vpf`, etc. VPA1 is little-endian, data-only. Header: magic `VPA1` (0), u32 header bytes=64 (4), u32 frame count 1–4096 (8), CRC32 of bytes [16,end) (12), u32 Nx/Ny/Nz (16,20,24), reserved u32=0 (28), f64 extent X/Y/Z (32,40,48), f64 density cap (56). Each 16-byte record is f64 strictly increasing nonnegative time, u32 complete VPF1 byte length (exact shared grid size), u32 CRC32 of the **entire** VPF1. Each loaded frame is decoded and its grid, cap and time matched. Same grid throughout, maximum 2,097,152 voxels. No filenames or executable content in index. CRC detects accidental corruption, not authenticity.

`FieldSequence.sample(time)` clamps to ends, returns a fresh Float32 field, exact keyframes or `f32(a + (b-a)*u)` computed in f64 per scalar. No automatic looping; no motion compensation. Callers choose keyframe cadence appropriate to motion. Rust/C++/C# use synchronous bounded loader callbacks; Python `FieldSequence.open(path)` and JS `openFieldSequence(url)` provide bounded file/fetch readers. Two **cached decoded** keyframes, plus an owned sample and temporary decode/upload allocations. Single owner; concurrent JS seeks rejected. On JS clear/dispose late results rejected; an external AbortSignal can cancel HTTP. GPU player owns a field but not the device or sequence. Two reusable field buffers at fixed geometry; after each awaited seek use a fresh `renderSource`, do not retain old source descriptors. WebGPU still needs CPU packing and upload on every seek and optical cache invalidation. No claim of GPU timing or motion compensated interpolation. Rust/C# source not yet compiled.
