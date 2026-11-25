# 제품 마일스톤 및 완료 게이트

코드 작성, 버전 변경, 연구 실행, Pages 배포는 제품 완료와 다르다. 실제 대표 실행 환경을 우선하며 모든 플랫폼 전수 테스트는 요구하지 않는다. 현재 진행 상태는 [WORK_STATUS](WORK_STATUS_KO.md)가 정본이다.

| 마일스톤 | 완료 조건 |
| --- | --- |
| M1 Runtime Foundation | 실제 native CPU 빌드·테스트, WASM 실행, 전체 cloud hero 밀도/광학/RGBA 동등성 |
| M2 Fluid Fidelity | 실제 Rust 실행, 운동량·압력의 영역 결합, 전단층·자연스러운 와류, 장애물, full-plume 시각·수치·비용 검증 |
| M3 Optical Fidelity | 실제 GPU 광학/깊이, 효과별 광학 및 입경·증발/응결 근사, 움직이는 유체 품질 |
| M4 Game Runtime | 대표 웹/게임 장면의 GPU 검증, 비용·메모리·동시 효과·LOD·수명주기 |
| M5 SDK Release | 검증된 실제 바이너리, 사용성·안정성, M1–M4 승인, 권리/배포 검토 |

## 교차 검증과 채택 원칙

- `contracts/cloud-hero.json`은 canonical cloud의 시드·크기·격자·카메라·광학·허용오차를 정의한다. 독립 생성 필드, 같은 기준 필드의 광학, end-to-end 결과를 따로 비교한다. 참조 이미지로 Rust 결과를 대체하지 않는다.
- M2의 보존 수송/CG/국소 분출 후보는 실제 Rust 실행과 외형을 검증해야 기본값으로 채택할 수 있다. fine/coarse scalar 연구는 압력·운동량 결합이 없으며 형상 오차로 미채택. 전체 영역 MAC/DST 연구 역시 자연스러운 플룸 품질이 부족하다.
- VPF1/VPA1 공유 데이터와 애니메이션 에셋은 독립적인 제품 기능이다. 파일 왕복이나 보간의 성공은 물리, 광학, 하드웨어 성능의 성공을 뜻하지 않는다.
- Airborne Smoke는 예술적 VFX 예제, Pages는 문서/데모 배포이다. 해당 결과를 물리 정확도나 상용 SDK 준비 완료의 증거로 사용하지 않는다.

실행: [검증 절차](VALIDATION_KO.md). 실제 native/WASM 및 hero parity 통과 후 `package_runtime_candidate.py`는 일치하는 영수증 기반 평가용 ZIP만 생성한다. 권리·제품 릴리스 판정은 별도다.
