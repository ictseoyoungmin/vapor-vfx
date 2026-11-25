# Fidelity Lab — current research

독립 연구 경로. SciPy MAC/DST reference는 실제 Rust MAC/SOR와 다르며 장애물 미지원. JS reference 광학은 `../bindings/web/fidelity.mjs`에 유지. 제품의 자동 fallback 아님.

Python 3.11+, `python -m pip install -r lab/requirements.txt`, Node 22. repo root에서:
```sh
python -m unittest discover -s lab/tests -v
python lab/transport_audit.py
python lab/resolved_source_lab.py --scales 1 3 --duration .35
node lab/render_source_lab.mjs reports/local/lab/source reports/local/lab/source
```
연구 생성물은 `reports/local/lab/`. 과거 장면 재현은 history ZIP의 원본 스냅샷 사용. `render_reference_fidelity.mjs`는 `fidelity/reference-medium`, `reference-turbulent`, `reference-high`, `reference-detail` 아래 실제 계산 데이터 필요. 일부 과거 렌더 실험은 광학 override를 유지하므로 새 제품 품질 기준으로 사용하지 않는다.

## 보존형 밀도 수송
`conservative_transport.py`: MAC face flux, monotonized central limiter, SSP-RK2, CFL substep, open boundary exterior scalar 0 및 경계 outflow 적분. 실제 analytic 3D Gaussian translation 결과는 [보고서](../reports/research-transport.json). MUSCL은 형상 L1 오차를 줄였으나 잔류량 오차가 MacCormack보다 커진 사례 존재. 질량 예산 closure는 물리적 잔류량 정확성과 다르다. dtype/구현 차이로 Python timing은 Rust/GPU FPS가 아니다. 실제 projected MAC plume, 장애물·다방향 유속, source/decay budget 비교 전 SDK 채택 보류.

다음: 분출 운동량 입력, 국소 물리 해상도, shear-layer roll-up, jet→puff 전환. 렌더링만으로 큰 유체 흐름을 대체하지 않는다.

## M2 결합 플룸 실험

```sh
python lab/coupled_density.py --seconds 1.5
node lab/render_coupled_density.mjs reports/local/lab/coupled-density reports/local/lab/coupled-density/renders
python lab/compose_coupled_density.py reports/local/lab/coupled-density
```
MacCormack + 기존 분출, MUSCL + 기존 분출, MUSCL + 원통 내부 샘플 적분 분출을 비교한다. 운동량·열원 및 압력 알고리즘은 같은 방식으로 유지하되, 각 밀도장의 부력 피드백 때문에 속도장은 달라질 수 있다. 독립 SciPy MAC/DST 및 JS optics 결과이며 Rust 수치 동등성은 별도 검증 대상. 실제 분석은 [결과](../reports/research-coupled-density.json)와 비교 이미지에 남겼다. 밀도 보존 개선을 고품질 외형으로 승인하지 않았다.

## 국소 운동량·열 분출과 압력 연구
```sh
python lab/pressure_audit.py
python lab/resolved_plume.py --effect cigarette_smoke --output reports/local/lab/resolved-plume/smoke
python lab/resolved_plume.py --effect exhaled_aerosol --output reports/local/lab/resolved-plume/aerosol
node lab/render_resolved_plume.mjs reports/local/lab/resolved-plume/smoke reports/local/lab/resolved-plume/smoke/renders
python lab/compose_resolved_plume.py reports/local/lab/resolved-plume/smoke
```
동일한 국소 격자에서 기존 momentum/heat, 물리 source, 물리 source+5% 회전 축방향 seed를 비교한다. 밀도는 모두 동일한 source 적분 및 보존 수송, 압력은 DST, 가시화는 JS Fidelity. aerosol도 같은 방식으로 render/compose 가능. 결과는 [플룸](../reports/research-resolved-plume.json), [압력](../reports/research-pressure.json). 전체 장면을 자른 결과로 외형 승인하지 않는다. Numba MAC 이류는 SciPy 참조 대비 실제 테스트로 비교했다.

### Fixed fine/coarse scalar interface
`python lab/nested_transport_audit.py` transfers a translating Gaussian across aligned 4:1 slabs using shared fine-face flux and area restriction. Bidirectional/area-consistency tests live in `lab/tests/test_nested_transport.py`. The velocity is prescribed, not coupled; uniform fine reference is substantially more accurate. No AMR, pressure, momentum or full plume adoption.

## Full-domain reduced-order VFX experiment
```sh
python lab/lagrangian_plume.py --seconds 4 --markers 500 --output reports/local/lab/lagrangian
node lab/render_lagrangian.mjs reports/local/lab/lagrangian reports/local/lab/lagrangian/renders
node lab/render_calibrated_plume.mjs reports/local/lab/lagrangian reports/local/lab/lagrangian/calibrated
```
Base / offset vortex rings / non-axisymmetric eddy packets with correlated dispersion use the same source integral and respective domain. These are prescribed kinematics with marker transport, not a pressure/momentum solve, adaptive mesh, or CFD benchmark. The wider domain and model differ from 0.19; outflow cannot be directly compared as solver accuracy. The [experiment](../reports/research-lagrangian.json) records six 4 s cases, four snapshots each. Original preset optics produce faint renderings. The [calibration](../reports/optical-calibration.json) is a separate art-direction experiment (fixed 2 s anchor and target opacity); inferred extinction is far above the original preset, not a measured material constant, and is NOT adopted. Neither appearance nor motion is accepted as high-fidelity; no change to production effect defaults.

## Animated cloud and full-domain audit
`lab/cloud_motion.py SOURCE.vpf OUTPUT --seconds 12 --fps 2 --speed 2`: evolves an isotropic Float32 source using discrete MAC curl and conservative MUSCL. Initial field is not regenerated. `node lab/render_cloud_motion.mjs OUTPUT RENDERS` renders real data via JS player with canonical cloud optics and comparison to the legacy noise evolution. `lab/full_domain_plume.py --effect exhaled_aerosol --seconds 3 --output PATH` runs a larger uniform independent MAC/DST domain; `node lab/render_full_domain.mjs PATH PATH/render` renders original optics. Neither proves Rust execution. The plume is still visually rejected.

The selected optional animation asset uses `lab/cloud_flowmap.py SOURCE.vpf OUTPUT`, which advects inverse coordinates then resamples the original field; correction is bounded to 2% and measured, not a locally conservative method. `lab/cloud_hero_deform.py PREVIEW.vpf HERO.vpf OUTPUT` and `node lab/render_hero_deform.mjs OUTPUT` evaluate a coarse inverse displacement on the canonical hero field. See `reports/cloud-motion.json`. `python tools/validate_sequence.py INDEX --build --native` requires actual Rust and checks sampled fields plus actual native renderer execution.

## Integrated visual example
See [Airborne smoke study](airborne_smoke/README.md). The independent artistic field and JS CPU optical renderer reproduce the approved V2 example. No production physics or core version change.
