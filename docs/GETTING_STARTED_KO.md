# 빌드·사용·엔진 통합

Python 3.11+, Rust 1.88+, OS 링커. Windows에는 Rust MSVC용 C++ 빌드 도구 필요. CPU 우선 `python tools/validate_runtime.py --build --modes cpu --capture`, `python tools/validate_native_fidelity.py --capture`, `python tools/profile_effects.py --modes cpu --capture`. 큰 실제 Rust 구름 캡처: `python tools/capture_native_cloud.py --hero` (실시간 성능 주장 아님).

## Python
`python -m pip install -e bindings/python` 후 `vapor_game.Simulation`, `create_effect`, `from vapor_game.fidelity import FidelityCPU`. `FidelityCPU().generate('cumulus_cloud', cells=(32,16,24))`는 실제 Rust 라이브러리 필요.

## JS/TS
`rustup target add wasm32-unknown-unknown`, `python tools/build.py --web` 후:
```js
import {loadVapor} from './bindings/web/vapor.mjs';
import {NativeFidelityCPU} from './bindings/web/native-fidelity.mjs';
const cpu = new NativeFidelityCPU(await loadVapor());
const cloud = cpu.generate('cumulus_cloud', {cells:[32,16,24], extent:[48,24,36]});
const frame = cpu.render(cloud,{width:96,height:60,steps:64,eye:[30,8,-50],target:[24,12,18]});
```
Rust exports 없으면 오류; JS reference로 전환하지 않는다. `node examples/node/fidelity.mjs cloud.rgba` 및 `python tools/validate_wasm_fidelity.py`로 실제 WASM 및 기존 JS 기준 데이터 검증. 현재 C/WASM 대역으로만 경계 검증됨.

## C# / Unity
`bindings/dotnet/Vapor.Runtime/Fidelity.cs`와 Unity `Runtime/Fidelity.cs`가 같은 C ABI 호출.
```csharp
using VaporGame;
var g = new FidelityGrid(32,16,24,new Double3(48,24,36));
var v = FidelityCPU.Generate(g,FidelityDensity.For(FidelityKind.Cloud,43));
var c = FidelityCamera.LookAt(new Double3(30,8,-50),new Double3(24,12,18),96,60,64);
var f = FidelityCPU.Render(v,c,FidelityOptics.Default);
```
C# 컴파일/Unity editor 미검증. 별도 CPU API이며 Unity 기본 게임 렌더 루프를 대체하지 않는다. Unity WebGL 연동 미구현.

## GPU 및 게임 엔진
`python tools/build.py --native --gpu --test --stage-adapters`, `python tools/validate_runtime.py --modes gpu hybrid --capture`, `python tools/profile_effects.py --modes cpu gpu hybrid --quality low --capture`.

- Unity: `adapters/unity/README.md`, UPM, P/Invoke, Built-in/URP atlas.
- Godot: `adapters/godot/README.md`, godot-cpp/GDExtension, 기존 async atlas.
- Unreal: `adapters/unreal/VaporGame/README.md`, UE5 플러그인 소스·Blueprint·HLSL. 완성 uasset 미포함.
- Web: `adapters/three/README.md`, WebGL atlas 또는 WebGPU direct/Fidelity. CPU/Hybrid는 Rust WASM 필요.

대표 엔진 한 곳에서 실제 프레임 비용과 장면 가림 검증 필요. 모든 플랫폼 전수 테스트는 필수 아님. `--allow-software`는 명시적 소프트웨어 GPU correctness 검사로서 하드웨어 성능이 아니다.

## 고품질 구름 전체 재현 (실제 Rust 비교)

Node.js 22 및 Rust 설치 후:
```sh
python tools/validate_cloud_equivalence.py --profile hero --build
```
`reports/local/cloud-equivalence/reference.png`는 JS 비교 기준, `rust.png`는 실제 Rust 실행 성공 시에만 생성된다. `validation.json`의 밀도/온도, isolated optics, end-to-end 결과가 모두 PASS여야 한다.

웹 GPU 직접 렌더링은 `python tools/build.py --web` 후 `python -m http.server 8000 --bind 127.0.0.1`를 실행하여 `/examples/fidelity-cloud/`에서 Rust WASM을 선택한다. JS reference는 명시 선택만 가능.
```js
import {GpuFieldVolume} from './bindings/web/gpu-field.mjs';
import {GpuFidelityVolumeRenderer} from './bindings/web/gpu-fidelity.mjs';
// cloud = NativeFidelityCPU.generate(...) 반환값; device는 호스트 소유
const source = await GpuFieldVolume.create(device, cloud);
const renderer = await GpuFidelityVolumeRenderer.create(source);
// renderer.render(hostView, cameraAndLightingOptions);
// renderer.dispose(); source.dispose(); device 해제는 호스트 책임
```
고품질 GPU 경로는 기존 GPU 광학의 근사 해상도 제한을 유지한다. Hero의 80% 조명 캐시는 CPU 전용 비교 설정이며 웹 GPU 기본값은 50%/24 light steps. 동일 이미지임을 보장하지 않는다. 대표 하드웨어 검증: `python tools/validate_cloud_webgpu.py --channel msedge`.

전체 대표 환경 점검: `python tools/release_gate.py --full-plume --channel msedge`. 평가 ZIP 생성 가능 조건은 실제 native+WASM 및 hero 동등성 PASS이며, SDK 릴리스가 아니다.

## Baked cloud / fog
Separate VPF1 asset ZIP can be opened without a Rust build. JS demo `/examples/fidelity-cloud/`: choose Baked VPF1, select `cloud.vpf`, start (requires WebGPU). For Unity rename to `cloud.bytes`, import as TextAsset, add `VaporBakedVolume` to an empty unit-scale object and assign `Vapor/VolumeBuiltIn` or `Vapor/VolumeURP`. Set optical parameters from the JSON sidecar; actual game lighting differs from the JS reference. Supports static data, not dynamic fluid; editor/shader unverified. C++17 header `include/vapor_field_asset.hpp` returns planar data and interleaved RG32F for host upload (Godot/Unreal integration not automatic).
```sh
python tools/validate_baked_cloud.py /path/to/field-assets --build
```
Uses actual Rust optics on the baked reference, independently of generator parity. Missing compiler returns BLOCKED; no generated Rust image substituted.

## Animated baked cloud (VPA1)
Extract `vapor_0.22_animated_cloud.zip` into the repository root (creates `assets/cloud-motion/`). Serve using `python -m http.server 8000 --bind 127.0.0.1`, open `/examples/animated-cloud/`, click Open then Play. Needs actual WebGPU for this demo, no Rust WASM needed. CPU offline playback: `from vapor_game.field_sequence import FieldSequence` (set PYTHONPATH to bindings/python); `s=FieldSequence.open('assets/cloud-motion/sequence.vpa'); f=s.sample(3.25)`. `f.native_fields()` can be passed to the existing actual Rust Fidelity renderer after building it. JS/C++/Python interpolation exercised; Rust and C# compiled execution and browser demo are pending. No engine FPS claim.

## 통합 예제
전체 ZIP을 한 번 압축 해제하면 현재 에셋까지 사용할 수 있다. `examples/airborne-smoke/index.html`은 더블클릭하여 바로 재생한다. 다른 예제는 프로젝트 루트에서 `python -m http.server 8000 --bind 127.0.0.1` 후 `http://localhost:8000/examples/`로 접근한다. [드론 연기 예제](../examples/airborne-smoke/README.md)의 CPU 검사기는 저장된 VPF1 3D 필드를 실제 렌더링하지만 실시간 유체나 Rust/GPU 검증은 아니다.

## 공개 사이트 미리보기
`python tools/build_pages.py --assets auto`로 `dist/pages/`를 만든다. `python -m http.server 8000 --bind 127.0.0.1 --directory dist/pages`로 확인한다. 자세한 배포 및 권리 검토는 [공개 가이드](PUBLISHING_KO.md)를 따른다.
