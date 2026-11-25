# 검증·증거·배포 게이트

| 명령 | 의미 |
|---|---|
| `python tools/check_sdk.py --source-only` | 제품 소스/ABI/fixture boundary/JS 회귀; Rust runtime 아님 |
| `python tools/check_sdk.py --source-only --lab` | 독립 연구 tests 추가 |
| `python tools/check_sdk.py --source-only --legacy` | history의 원본 46개 해시/정적 검사/156 PCHIP golden 재감사 |
| `python tools/check_sdk.py --require-runtime` | 실제 native CPU와 Fidelity parity 필수 |
| `python tools/check_sdk.py --require-runtime --wasm-runtime` | 실제 WASM smoke 및 Fidelity parity 추가 |
| `python tools/check_sdk.py --require-runtime --gpu-runtime` | 실제 native GPU/Hybrid 추가 |

실제 바이너리는 source fingerprint와 artifact SHA-256 영수증으로 확인. C/WASM fixture, GPU host doubles는 테스트 전용. 모든 required gate 통과 전 `BLOCKED`/`FAIL`은 성공 아님. `production_release_ready=false` 유지.

P0: 실제 CPU core 및 Fidelity 필드/alpha/RGBA 동등성. P0: 실제 GPU/Hybrid와 시간별 연무 결과. P1: 대표 엔진 하나에서 프레임 비용·메모리·수명주기·깊이 검증. 시각 개선은 같은 카메라·조명·시드·시간에서 확인하고, 테스트 개수로 대체하지 않는다.

`reports/validation-current.json` 현재 검증; `reports/research-transport.json` 이번 독립 연구; `reports/local/` 생성물(패키지 제외); `history/` 이전 증거. 과거 보고서의 경로와 상태는 당시 기준이다.

## 마일스톤 실행 검증

`python tools/milestone_gate.py --milestone all`은 실제 빌드와 CPU 테스트, native Fidelity parity 및 구름 캡처, WASM parity, 새 Rust CPU A/B까지 순서대로 수행한다. `--native-only`는 WASM 생략을 명시적으로 기록한다. `reports/local/milestones/run-*/gate.json`에서 source fingerprint, 개별 결과 및 로그를 확인한다. 실행 성공은 시각 품질 승인과 별개다. GPU는 사용자 PC의 기존 검증 명령으로 검사한다.

## M2 resolved candidate
`python tools/validate_resolved_plume.py --seconds 4`는 실제 Rust 소스에서 `m2_resolved`를 빌드하여 2 효과 × 3 모델을 실행한다. 출력은 새 run 디렉터리, 실제 PPM → PNG, 스텝별 metrics와 파일 해시. `--effects cigarette_smoke --models matched --seconds 0.25`는 짧은 실행 probe이며 마일스톤 gate에 포함한다. CG f32 압력 residual ≤ max(initial×1e-4,1e-5), 실제 projected velocity divergence ≤ max(initial×2e-4,2e-5), clamp 0 및 밀도 closure를 검사한다. 전체 플룸 캡처의 국소 경계 outflow 5% 초과는 부적합으로 기록(시각 검수와 별도). 5%는 공학적 채택 기준이며 일반적인 열린 영역의 물리 유출을 실패로 정의하지 않는다. 실제 compiler 없으면 BLOCKED, 다른 솔버로 대체 금지. `--seconds 4`의 여섯 실행은 대표 probe보다 비용이 크다. Lab의 DST vs SOR/CG 독립 비교는 [압력 보고서](../reports/research-pressure.json)이며 Rust 성능이나 실행 증거가 아니다.

## Full cloud and M5 evaluation gate
`validate_cloud_equivalence.py --profile hero --build` regenerates the exact 0.13 scene, checks all density and temperature voxels, isolated optics and end-to-end alpha/RGBA. Reference-only result cannot certify Rust. `validate_cloud_webgpu.py` requires actual receipt-bound WASM, renders the field with the existing GPU optics, compares same field against JS CPU renderer at matched settings (not against the 80% hero), checks camera cache reuse, depth clipping, field replacement and wall completion timing. Its timing is not game FPS. `release_gate.py --full-plume` runs the representative native/WASM/WebGPU and GPU/Hybrid path, records M2–M5 incompleteness. Package creation requires matching source and artifact receipts plus all four small fidelity cases and full hero parity. Never sets `production_release_ready=true`.

## VPF1 data parity is not runtime parity
`node tools/bake_field_assets.mjs OUTPUT hero` produces cloud/fog VPF1 + sidecar and actually renders before and after decoding. Compare exact byte roundtrip and RGBA/alpha. Python and C++ verify entire field bytes/bits; Rust and C# remain source-only. `python tools/validate_baked_cloud.py OUTPUT --build` checks exact asset and reference hashes, actual receipt-bound Rust renderer with identical field and canonical optics; generation parity remains `validate_cloud_equivalence.py --profile hero --build`. See [asset report](../reports/field-assets.json). Reduced-order plume experiment is independent and not a substitute for M2. Original optics and separate calibration results must not be conflated.

## Animated playback gate
VPA1 index validation, corrupt record/frame rejection, strict time ordering, interpolation and exact endpoints, mutable returned copy isolation, two-frame cache and JS pending cancellation. Python-generated shared golden tested against actual JS/Python/C++ readers; Rust fixture tests pending compiler. GPU upload allocation/failure tests use explicit device test double, not a shader/runtime measurement. Lab verifies discrete face divergence, zero outer normal flux, scalar conservation, unchanged starting field, actual 25 rendered frames per candidate and 49 cross-language sample hashes; inverse flow map normalization and gradient-energy loss are reported separately. The expanded domain plume audit uses independent MAC/DST and original preset; reduced boundary loss alone does not meet visual acceptance. No production readiness certification.

## Airborne Smoke example
`python lab/airborne_smoke/rebuild.py --frame 56`은 실제 독립 Python+JS 볼륨 프레임을 생성한다. `node lab/airborne_smoke/inspect_audit.mjs`는 전체 패키지의 세 VPF1 필드 왕복·광학 및 캐시를 검증한다. 영상 및 검사기 증거는 `reports/airborne-example.json`. 실제 Rust/WGSL 검증은 별도이며 이번 예제가 물리 정확도나 SDK 실시간 성능을 입증하지 않는다.

## Pages 배포 검사
`python -m unittest discover -s tests -p test_pages.py`와 `python tools/build_pages.py --assets auto`는 정적 링크, 상대 경로, 선택 에셋, 공개 범위, 템플릿 구성을 검사한다. 브라우저 검사와 사이트 검증 결과는 `reports/pages-preview.json`에 별도 기록한다. 이 검사는 native/GPU/게임 품질을 승인하지 않는다.
