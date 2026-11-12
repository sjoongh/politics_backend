# 공유 유입 점검·검증 — 2026-11-11

## 2026-11-12 배포 재개
- 사용자 `진행해봐`에 따라 커밋·PR·운영 배포와 실제 콘텐츠 진입 검증 진행.
- origin/main 동기 확인: backend dd69b02, frontend 7be4c0a. 이전 로컬 수정 이외 추가 코드 변경 없음.
- 운영 기사 목록/이슈 목록 HTTP 200, success=true. 전일 429는 현재 재현되지 않음.
- 백엔드 전체 283 passed, 프런트 73 passed. 프로덕션 빌드 성공(기존 경고 2개 유지).
- 스냅샷 Actions 43128600991 성공. 뉴스 수집 Actions 43127896497 실패는 별도 확인 중.

## 변경
- backend routers/share_router.py: 문서가 없으면 기본 브랜드 이미지와 홈으로 이동. 조회 장애는 no-store와 원래 콘텐츠 목적지를 유지.
- frontend src/pages/Today.jsx: 기사 딥링크를 조회 성공까지 보존. 실패/삭제 안내, 다시 시도, 로딩 상태, 화면 이동 후 늦은 응답 무시.
- frontend scripts/share-loop-check.cjs: 운영 요청을 차단한 격리 브라우저에서 실제 backend HTML + 합성 API로 회귀 검증.

## 실행 근거
- `.venv/bin/python -m pytest tests/test_share_router.py tests/test_share_render.py tests/test_og_image.py tests/test_read_budget_api.py tests/test_http_cache.py -q`: 49 passed. 기존 라이브러리 경고 4개.
- `CI=true npm test -- --watchAll=false --runInBand`: 15 suites / 73 passed.
- `CI=true npm run build`: 기존 LoginForm.jsx 미사용 Typography, MyPage.jsx 중복 border 경고를 오류로 처리해 실패. 이번 변경과 무관하여 수정 범위에 포함하지 않음.
- `CI=false npm run build`: 빌드 통과, 위 기존 경고와 Browserslist 데이터 노후화 알림 존재.
- `node scripts/share-loop-check.cjs`: 390/1280px 각각 6개 시나리오 통과. 실제 share HTML → 기사 리더 → 서비스 URL 공유, 조회 실패→재시도, 누락 기사 안내, 다른 화면 이동 후 늦은 응답 무시, 이슈 링크→상세→공유, 삭제 링크→홈. 브라우저 runtime error 없음.
- 최초 지연 응답 검증은 URL 변경만 기다려 React 화면 전환 완료 전에 응답을 반환했다. 로딩 상태의 실제 화면 제거까지 기다리는 것으로 검증 조건을 고친 후 통과.
- `/tmp/share-loop-error-390.png`, `/tmp/share-loop-error-1280.png` 시각 확인. 모바일 버튼 줄바꿈 발견 후 재시도를 반복하는 오류 문장을 줄임.

## 운영 관측과 한계
- https://koreanpolitical.web.app 및 og-default.png: HTTP 200, 기본 이미지 공개 접근 확인.
- `/health`: 200. 기사 목록과 이슈 목록: HTTP 500 / `429 Quota exceeded.`.
- 공유 HTML: 200이지만 no-store 기본 카드. DB 조회 성공으로 판정하지 않음.
- https://github.com/sjoongh/politics_backend/actions/runs/42944726252 : 스냅샷 0/5, 기존 정상본 없음. API 장애 때문에 생성되지 않았으며 재실행하지 않음.
- 운영 DB 데이터 쓰기, 수집 재실행, 과금 변경, 메신저 발송, 광고 집행 없음.
- 카카오/페이스북 실제 카드, 현재 운영 콘텐츠 진입은 미검증. 쿼터 회복 후 검증 필요.
- 코드 수정은 로컬 작업트리에 보존. 커밋·push·배포 미실시.

## 홍보 재개 기준 / 측정
1. 기사/이슈 목록과 상세가 정상 응답하고, 실제 콘텐츠의 공유 HTML·이미지·최종 상세 진입이 일치해야 한다.
2. 정적 스냅샷 5개 생성 상태와 최신 시각 확인. 최신 코드의 읽기 예산 수정만으로 쿼터 회복을 단정하지 않는다.
3. 실제 카카오/페이스북 수신 카드와 진입을 확인한다(현재 미실시).
4. GA4 share 이벤트는 이미 있다. 현재 공유 수·신규 방문·재방문 기준값은 조회하지 않았으며 공유 기여 유입률은 별도 유입 식별 없이 계산할 수 없다. 홍보 효과는 미측정.
