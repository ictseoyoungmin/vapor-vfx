# 아키텍처와 폴더 소유권

Vapor는 Rust 제품 SDK와 독립 Fidelity Lab을 병행 개발한다. 두 경로는 프리셋·필드·검증 계약을 공유하되, 참조 구현이 제품 런타임의 실패를 대체하지 않는다.

## 모듈 구조

```text
Vapor/
├─ crates/                Rust 제품
│  ├─ vapor-core/         MAC 물리·효과·CPU Fidelity
│  ├─ vapor-backend/      CPU/GPU/Hybrid 실행·전송
│  └─ vapor-ffi/          C ABI/WASM exports
├─ shaders/               공통 WGSL 원본
├─ effects/               JSON 프리셋 원본
├─ include/               C/C++ 계약 원본
├─ bindings/              Python·JS/TS·.NET
├─ adapters/              Godot·Unity·Unreal·Three.js
├─ lab/                   독립 연구 코드와 실험·tests
├─ contracts/             공유 장면/알고리즘/해시 계약
├─ fixtures/              소형 고정 기준 데이터
├─ examples/              실제 예제 및 뷰어
├─ assets/                현재 VPF1/VPA1 선택 에셋
├─ site/                  공개 사이트 템플릿·카탈로그·미디어
├─ tools/                 빌드·동기화·검증·Pages 생성
├─ tests/                 제품 소스/ABI/회귀 검사
├─ docs/                  현재 기술 문서
├─ reports/               소형 검증 증거; local/은 생성물
├─ dist/pages/            생성된 정적 사이트(Git 제외)
├─ history/               선택적 별도 보존 자료(Git 제외)
└─ project.json           배포/코어/바인딩/Lab 버전
```

제품 호출 방향은 adapters → bindings/C ABI → vapor-ffi → vapor-backend → vapor-core이다. GPU 호스트는 `shaders/`의 동기화된 복제본을 사용한다. 제품은 `lab/` Python을 가져오지 않는다. JS `bindings/web/fidelity.mjs`는 독립 CPU 구현이며 `native-fidelity.mjs`는 실제 Rust WASM 호출 경로이다.

| 영역 | 제품 | 독립 연구/검증 |
| --- | --- | --- |
| 유체 | Rust MAC/SOR, WGSL, coarse CPU + fine GPU | SciPy MAC/DST, 독립 수송 실험 |
| 구름·안개·먼지 | Rust procedural / 선택 Fidelity | JS Fidelity |
| Float32 광학 | Rust CPU / WebGPU Fidelity 소스 | JS CPU 렌더러 실행 |
| 에셋 | VPF1 필드 / VPA1 순서 데이터 | 실제 데이터 생성·왕복·A/B |

## 계산 및 렌더링 경로

- 기본 CPU·GPU·Hybrid 및 ABI는 그대로 유지한다. Hybrid는 CPU coarse MAC → GPU fine scalar의 단방향 연결이며 양방향 운동량 결합이 아니다.
- M2 Rust 직접 API 후보는 `transport.rs`의 보존형 밀도 수송, `plume.rs`의 물리 분출 영역, `pressure.rs`의 열린 도메인 CG를 사용한다. `new_conservative_density`, `new_converged_density`, `new_resolved_plume`은 명시적으로 선택한다. 기존 `new`는 변경되지 않았으며 후보의 장애물·AMR·GPU/ABI 이식은 미완료다. 상세 계약은 [API](API_CONTRACT_KO.md)를 따른다.
- Native Fidelity는 stateless C ABI 호출마다 광학 캐시를 준비한다. 직접 Rust generator/renderer는 재사용 가능하다. 실제 Rust 실행 검증은 남아 있다.
- `GpuFieldVolume`은 Float32 필드를 호스트 WebGPU 장치의 버퍼(vec4)로 업로드한다. `GpuFidelityVolumeRenderer`는 광학 깊이 캐시를 카메라/평행이동 변화에 재사용하고 새 필드가 커밋될 때 무효화한다. GPU 광학과 GPU 유체 계산은 별개이며 최초 및 갱신 시 CPU→GPU 전송이 있다.

## 볼륨 데이터와 예제

Lab → VPF1/VPA1 및 장면 메타데이터 → 독립 데이터 리더 → Float32 API → 렌더러. VPF1은 정적 필드, VPA1은 순차 시간 인덱스다. `field_sequence` 플레이어는 인접 두 키프레임을 캐시하고 선형 보간한다. GPU 플레이어는 두 버퍼를 재사용하며 매 seek에서 필드 업로드와 광학 캐시 갱신이 필요하다. Native C#/Rust 실행은 미검증이다. Unity 정적 baked adapter는 자체 셰이더를 사용하므로 데이터 일치가 픽셀 일치를 보장하지 않는다.

`lab/cloud_motion.py`는 정해진 MAC curl 속도에서 보존형 이류를 계산하고, `cloud_flowmap.py`는 역좌표 이류 후 원본을 재샘플링한다(전체량 보정, 국소 보존 아님). `cloud_hero_deform.py`는 고해상도 원본에 변형을 적용한다. 모두 기상/운동량 방정식을 함께 푸는 모델은 아니다.

`lab/airborne_smoke/`는 예술적 볼륨과 렌더링 레시피, `examples/airborne-smoke/`는 독립 영상 플레이어 및 저장 필드 CPU 검사기이다. 제품 실시간 유체 솔버와 구분한다. `contracts/cloud-hero.json`은 구름의 원본 비교 장면으로 유지한다.

## 배포와 웹사이트

정본은 `effects/presets.json`, `shaders/`, `include/`, `bindings/dotnet/`. 복제본은 `tools/generate_effects.py`, `tools/sync_distribution.py`로 동기화한다. 공개 사이트는 `site/catalog.json`과 템플릿에서 `tools/build_pages.py`로 생성한다. 웹 예제와 필요한 바인딩만 상대 경로로 복사하며 선택 에셋이 없으면 로컬 실행으로 명시한다. `site/`에 제품 소스/예제/대용량 필드를 이중으로 저장하지 않는다. `dist/pages/`는 배포 산출물이며 엔진 바이너리·history·실험 로그를 포함하지 않는다.

제품 릴리스, Pages 공개, 연구 결과 재현은 독립 상태로 관리한다. Pages 빌드 성공은 M1–M5를 닫지 않는다. 문서 변경 이력은 `CHANGELOG.md`, 현재 기술 결정은 해당 문서, 상세 실험 결과는 보고서가 담당한다.
