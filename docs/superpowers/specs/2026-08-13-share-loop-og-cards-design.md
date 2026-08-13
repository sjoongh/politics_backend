# 공유 루프 완결셋 — 동적 OG 카드 설계

- 날짜: 2026-08-13
- 범위(A): 동적 OG 카드 + 뉴스 공유 앱 딥링크화(원문 유출 차단) + 기사 딥링크
- 목표: 이슈/기사 링크를 카톡·페북에 공유하면 **콘텐츠별 미리보기 카드**가 뜨고, 누르면 앱(SPA)의 해당 콘텐츠로 진입 → 사용자 1명이 새 사용자를 데려오는 성장 고리 복원
- 관련: [[briefingkorea-ui-overhaul]], v1 1차소스엔진 `2026-06-16-primary-source-engine-design.md`

## 배경 / 문제

현재 공유 루프가 파편적으로 끊겨 있음(teardown 2026-08-13):
1. **OG 태그 전무** — `politics_front/public/index.html`에 `description` 한 줄뿐. 공유 링크에 미리보기 카드가 안 뜸. 게다가 CRA SPA라 정적 태그로는 콘텐츠별 카드 불가.
2. **뉴스 공유가 원문 유출** — `NewsReaderModal.jsx`가 `current.source_url`(언론사 링크)을 공유 → 경쟁사로 트래픽.
3. (이슈 공유는 `IssueDetail`이 `/?issue=<id>`로 앱 딥링크는 하지만 카드가 안 떠서 클릭률 바닥)

## 아키텍처

기존 Vercel FastAPI 백엔드(`politicsbackend-ruby.vercel.app`, 개인 Vercel = sjoongho@wishket.com)가 공유 URL을 렌더한다. **커스텀 도메인/Firebase Function/Blaze 불필요.** 도메인·이미지·이동목적지는 env로 분리해 교체 가능.

```
카톡/페북 봇  → GET {SHARE_BASE}/share/issue/{id}  → 200 OG HTML (카드 렌더)
사람이 카드 탭 → GET 같은 URL                       → 같은 200 HTML + JS location.replace
                                                     → {WEB_APP_URL}/?issue={id} (SPA)
```

핵심 원칙(codex 교차검토 반영):
- **302 리다이렉트 금지** — 크롤러가 따라가 OG 없는 SPA를 읽어버림. OG HTML을 **200**으로 반환하고 사람은 JS로 이동.
- `og:url`은 최종 SPA URL이 아니라 **공유 URL 자체**로 고정(캐시·집계 안정).
- `og:image`는 절대 HTTPS URL, 공개 접근, 1200×630.
- 봇 UA 판별에 핵심 로직을 의존하지 않음 — "JS 미실행 크롤러 vs JS 실행 브라우저" 차이를 활용(양쪽에 같은 200 HTML을 주고, 이동은 JS로만).
- 카카오·FB는 OG를 강하게 캐시함(제목 변경 즉시 반영 안 될 수 있음 — 알려진 한계로 수용).

## 컴포넌트

### 백엔드 (politics_backend)

**`utils/share_render.py`** (순수함수, TDD 대상)
- `render_share_html(title, description, image_url, share_url, redirect_url) -> str`
- 책임: HTML escape, 제목 60자·설명 150자 절단, OG/twitter 메타 태그 조립, 사람용 `<script>location.replace(redirect_url)</script>` + `<noscript><a href=redirect_url></noscript>` 폴백 포함한 완성 HTML 문서 반환.
- 의존: 없음(순수 문자열). → 단위테스트 용이.

**`routers/share_router.py`**
- `GET /share/issue/{issue_id}` , `GET /share/article/{article_id}`
- Firestore에서 이슈/기사 조회(기존 `issue_service`·`news_service` 재사용) → 필드 매핑(title, summary→description) → `render_share_html` 호출 → `HTMLResponse(200)`.
- 응답 헤더 `Cache-Control: s-maxage=600, stale-while-revalidate` 부여(Firestore 호출 절감).
- main app에 라우터 등록(prefix 없이 `/share`).

**설정(env, `collect_config` 또는 settings)**
- `WEB_APP_URL` (기본 `https://koreanpolitical.web.app`) — 사람 이동 목적지
- `SHARE_BASE_URL` (기본 `https://politicsbackend-ruby.vercel.app`) — og:url 고정용
- `OG_DEFAULT_IMAGE` (기본 `{WEB_APP_URL}/og-default.png`) — 브랜드 기본 이미지 절대 URL

### 정적 자산
- `politics_front/public/og-default.png` (1200×630 브랜드 이미지) → firebase deploy 시 `koreanpolitical.web.app/og-default.png`로 공개 HTTPS 서빙. 이미지 소스는 구현 착수 시 확정(제작 또는 사용자 제공).

### 프론트 (politics_front)
- **`NewsReaderModal.jsx`** `share()`: 공유 URL을 `current.source_url` → `${SHARE_BASE}/share/article/{current.id}`로 교체. (원문 열기 버튼 `openOriginal`은 그대로 유지)
- **`IssueDetail.jsx`** `handleShare()`: 공유 URL을 `${window.location.origin}/?issue=${issueId}` → `${SHARE_BASE}/share/issue/${issueId}`로 교체.
- **`App.jsx`**: 기존 `?issue=` 딥링크 처리에 **`?article=<id>`** 분기 추가 → 해당 기사 `NewsReaderModal` 오픈.
- **env** `REACT_APP_SHARE_BASE_URL` (기본 백엔드 URL).

## 데이터 흐름 (이슈 공유 예)
1. 사용자가 IssueDetail에서 공유 탭 → `navigator.share({url: '{SHARE_BASE}/share/issue/{id}'})`.
2. 수신자가 카톡에 붙임 → 카카오 봇이 URL GET → FastAPI 200 HTML(og:title=이슈 제목, og:description=요약, og:image=기본, og:url=공유URL) → 카드 렌더.
3. 수신자가 카드 탭 → 브라우저가 같은 URL GET → 같은 200 HTML → JS `location.replace('{WEB_APP_URL}/?issue={id}')` → SPA가 이슈 상세 오픈.

(기사 공유도 동일, `/share/article/{id}` → `?article={id}`)

## 에러 처리
- 없는/삭제된/비공개 콘텐츠 → **200 + 기본 브랜드 OG**(제네릭 제목 "브리핑 코리아 · 정치 브리핑") + `WEB_APP_URL` 홈으로 이동. 크롤러에 404 주지 않음(카드 죽음 방지).
- Firestore 조회 예외 → 동일 기본 OG 폴백 + 로깅.
- 제목/설명은 항상 escape + 길이 제한.

## 테스트
- **단위(순수, TDD)**: `share_render` — escape(따옴표/꺾쇠), 제목·설명 절단, redirect_url 삽입, noscript 폴백 존재, 값 없을 때 기본 폴백.
- **통합**: `share_router` — 스텁 이슈 주입 시 200 + body에 실제 og:title + 올바른 redirect URL; 없는 이슈 → 기본 OG 200; Cache-Control 헤더 존재.
- **수동 검증**: 배포 후 `curl`로 메타태그 확인 + 카카오/페이스북 공유 디버거로 실카드 확인 + 실제 카톡 공유 1회.

## 범위 밖 (각각 별도 사이클)
- 카카오 SDK 배선(앱키·도메인 등록 필요) — `SummaryCard.jsx`의 죽은 `Kakao.Share` 코드 정리 포함
- 안드로이드 App Links(`assetlinks.json` + intent-filter autoVerify, 서명키 지문 필요)
- 이슈별 동적 OG 이미지 생성(정당색/표결집계 렌더) — 효과 확인 후 v2

## 성공 기준
- 이슈/기사 공유 링크를 카카오/페북 디버거에 넣으면 **콘텐츠별 제목·설명 + 브랜드 이미지 카드**가 렌더된다.
- 뉴스 공유가 더 이상 원문 URL로 새지 않고 앱으로 유입된다.
- 카드 클릭 시 SPA의 해당 이슈/기사가 열린다.
- 없는 콘텐츠에도 카드가 깨지지 않고 기본 카드가 뜬다.
