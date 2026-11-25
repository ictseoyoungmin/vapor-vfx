# 현재 작업 상태

Distribution 0.24 · Rust core 0.22.0 · C ABI v1 · Lab core 0.22. 이번 revision은 GitHub 공개 준비, 문서 정돈, 예제 카탈로그와 Pages 생성이다. 제품 코어, 바인딩, 셰이더, 연구 알고리즘의 변경을 주장하지 않는다.

| 목표 | 상태 | 다음 승인 조건 |
| --- | --- | --- |
| M1 | BLOCKED | 실제 Rust native/WASM 및 cloud parity |
| M2 | IN_PROGRESS | 기존 보존형 수송/CG 후보 실제 검증; full-plume 시각 품질 개선 |
| M3 | IN_PROGRESS | 실제 GPU 고품질 광학 및 효과별 물리·광학 보정 |
| M4 | IN_PROGRESS | 대표 게임 장면 성능·통합, 엔진/장치 실행 |
| M5 | NOT_READY | 실제 검증 바이너리, 릴리스·권리 승인 |

이전 정성적 추정 Lab 약 85%, Rust SDK 약 51%를 유지한다. 목표 90%/55% 미충족이며 문서/사이트만으로 제품 진행률을 높이지 않는다. [목표 평가](../reports/target-assessment.json)는 기존 측정/판단에 대한 기록이다.

## 근거와 차단 요소

- JS 구름/안개, VPF1/VPA1 JS/Python/C++ 데이터 및 애니메이션 참조 결과는 실제 실행 검증됨.
- Airborne V2 film/저장 필드의 JS CPU optics는 실행 증거가 있음. 이는 예술적 VFX이며 실제 유체 런타임이 아님.
- Rust/C# 도구체인은 기존 전달 환경에서 없었고 실제 native/WASM, 하드웨어 GPU/Hybrid, 게임 에디터는 검증되지 않음. 기존 보고서를 새 런타임 실행처럼 수정하지 않음.
- 공개 사이트는 source-only 또는 선택 에셋으로 생성 가능. 권리 검토/라이선스 결정/원격 CI는 아직 필요함. GitHub 업로드 및 Pages 공개를 수행하지 않음.

## 다음 작업

1. 실제 Rust 컴파일 및 CPU·WASM parity를 원격 또는 로컬 CI에서 수행하고 결함 수정.
2. M2의 전체 플룸 형상/난류와 M3의 실제 효과 광학을 개선·검증.
3. 대표 장치의 실제 GPU 및 게임 비용을 확인하고 배포 범위를 확정.

[마일스톤 종료 조건](MILESTONES_KO.md) · [검증 절차](VALIDATION_KO.md) · [공개 체크리스트](PUBLISHING_KO.md)
