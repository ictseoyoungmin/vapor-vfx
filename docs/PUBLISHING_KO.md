# GitHub 공개 및 Pages 운영

## 공개 전 판정

현재 공개 권장 범위는 **experimental source / research preview**이다. Rust 및 GPU 바이너리의 정상 실행이나 상용 게임 준비 완료를 주장하면 안 된다. Pages 공개는 배포 준비와 별개다.

- [ ] 원본 v18, 코드, 이미지/영상, 에셋, 라이브러리 및 제3자 자료의 재배포 권리 확인
- [ ] 권리 확인 후 LICENSE/NOTICE 및 필요한 의존성 고지 작성. 이 패키지는 라이선스를 임의로 부여하지 않음
- [ ] 최초 GitHub 저장소는 경량 소스 ZIP으로 구성; 대용량 필드는 별도 데이터 ZIP/릴리스 에셋으로 관리
- [ ] 실제 native CPU/WASM CI 결과 확인; 제품 alpha 명칭/사용 범위 확정
- [ ] 공개 Pages 예제 및 대표 브라우저의 WebGPU 동작을 별도 검토

## 사이트 파일 구조

`site/`는 사이트 템플릿/카탈로그/실제 프로젝트 미디어의 정본이다. `dist/pages/`는 생성된 정적 사이트로 Git 추적하지 않는다. `examples/`, `bindings/web/`, 필요한 계약과 에셋은 빌드 시 상대 경로로 복사된다. 같은 제품 파일을 별도로 유지하지 않는다. 내부 reports, history, Rust 소스 및 네이티브/WASM 바이너리는 사이트 출력에 넣지 않는다.

```sh
python tools/build_pages.py --assets auto
python -m http.server 8000 --bind 127.0.0.1 --directory dist/pages
```

| 옵션 | 의미 |
| --- | --- |
| `--assets none` | 경량 사이트. 실제 film, CPU reference, scene-depth 및 실험 GPU 예제. 필드가 필요한 데모는 로컬 사용 안내 |
| `--assets auto` | 완전한 선택 에셋 그룹만 포함. 원본 데이터 없이 링크를 노출하지 않음 |
| `--assets full` | 모든 사이트 에셋 그룹 요구. 전체 SDK가 필요하며 누락 시 실패 |

사이트의 기본 주소는 프로젝트 하위 경로(예: `https://<owner>.github.io/<repository>/`)를 지원한다. 사용자 지정 도메인이나 저장소명은 추정하지 않는다. site 템플릿 자체를 배포하지 말고 생성된 디렉터리 내용을 배포한다.

## GitHub Actions로 배포

1. GitHub에 권한이 있는 저장소를 만들고 정리한 소스를 push한다. 공개 전 라이선스/고지 검토 및 실제 CI를 권장한다.
2. Repository → Settings → Pages → Build and deployment → Source: **GitHub Actions**.
3. Actions → Pages preview → Run workflow에서 재배포 권리가 확인된 경우에만 `rights_confirmed`를 선택한다. `asset_mode`는 일반적으로 `auto`다.
4. 빌드/경로 검사 및 `github-pages` 환경의 승인 후 배포한다. workflow는 push만으로 공개하지 않는다. 기본 브랜치 이외의 ref는 배포하지 않는다.

별도 배포용 Pages ZIP을 사용할 경우에는 그 내용을 Pages용 브랜치의 루트로 옮겨도 된다. 이 경우 GitHub의 branch publishing을 선택한다. 둘 중 한 방식만 사용한다. 대용량 필드 전체를 source Git history에 넣을 필요는 없다. full 사이트 자체의 전송량은 클 수 있으므로 공개 범위 선택은 운영자가 한다.

공식 참고: [Publishing source](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site), [Custom workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).
