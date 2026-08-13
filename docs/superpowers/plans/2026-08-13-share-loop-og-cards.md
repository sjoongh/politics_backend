# 공유 루프 OG 카드 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 이슈/기사 공유 링크에 콘텐츠별 OG 미리보기 카드가 뜨고, 눌러 앱으로 진입하게 만들어 공유 성장 고리를 복원한다.

**Architecture:** 기존 Vercel FastAPI 백엔드에 `/share/*` 라우트를 추가해 크롤러에는 OG 태그 HTML(200), 사람에게는 JS로 SPA 이동을 준다. 프론트는 공유 URL을 이 엔드포인트로 바꾸고(뉴스 원문 유출 차단) `?article=` 딥링크를 추가한다. 도메인·이미지는 env로 분리한다.

**Tech Stack:** Python/FastAPI (backend), React/CRA (frontend), Firestore, pytest, Firebase Hosting + Vercel.

## Global Constraints

- **302 리다이렉트 금지.** 공유 라우트는 항상 `200` OG HTML을 반환하고, 사람 이동은 JS `location.replace`로만 한다(크롤러가 리다이렉트 따라가 OG 없는 SPA를 읽는 것 방지).
- `og:url`은 최종 SPA URL이 아니라 **공유 URL 자체**로 고정한다.
- 제목·설명은 항상 HTML escape + 길이 제한(제목 60자, 설명 150자).
- 없는/삭제된 콘텐츠에도 `404`가 아니라 `200` + 기본 브랜드 OG를 반환한다.
- `db` import는 `from firebase.firebase_config import db`. 이슈 컬렉션 `"issues"`, 기사 컬렉션 `"articles"`.
- 순수 로직(`share_render`)은 Firestore·FastAPI에 의존하지 않는다. 라우트의 Firestore 접근은 `_fetch_*` 함수 seam으로 분리해 테스트에서 monkeypatch 한다(라우터 import가 firebase를 건드리지 않도록 db import는 함수 내부 지연 import).
- env: `WEB_APP_URL`(기본 `https://koreanpolitical.web.app`), `SHARE_BASE_URL`(기본 `https://politicsbackend-ruby.vercel.app`), `OG_DEFAULT_IMAGE`(기본 `{WEB_APP_URL}/og-default.png`), 프론트 `REACT_APP_SHARE_BASE_URL`(기본 백엔드 URL).

---

## Task 1: OG HTML 순수 렌더러 (`utils/share_render.py`)

**Files:**
- Create: `politics_backend/utils/share_render.py`
- Test: `politics_backend/tests/test_share_render.py`

**Interfaces:**
- Consumes: 없음(순수 함수, 표준 라이브러리만).
- Produces: `render_share_html(*, title, description, image_url, share_url, redirect_url) -> str`
  - 완성된 HTML 문서 문자열 반환. title/description이 빈 값이면 기본 문구 사용.

- [ ] **Step 1: Write the failing test**

```python
# politics_backend/tests/test_share_render.py
from utils.share_render import render_share_html

BASE = dict(
    title="테스트 이슈",
    description="요약 설명",
    image_url="https://koreanpolitical.web.app/og-default.png",
    share_url="https://politicsbackend-ruby.vercel.app/share/issue/abc",
    redirect_url="https://koreanpolitical.web.app/?issue=abc",
)

def test_includes_og_title_and_url():
    h = render_share_html(**BASE)
    assert '<meta property="og:title" content="테스트 이슈">' in h
    assert '<meta property="og:url" content="https://politicsbackend-ruby.vercel.app/share/issue/abc">' in h
    assert '<meta name="twitter:card" content="summary_large_image">' in h

def test_escapes_html_in_title():
    h = render_share_html(**{**BASE, "title": '<script>alert(1)</script>'})
    assert "<script>alert(1)</script>" not in h
    assert "&lt;script&gt;" in h

def test_clips_long_title_and_description():
    h = render_share_html(**{**BASE, "title": "가" * 100, "description": "나" * 300})
    # og:title content 길이(… 포함) 61자 이하
    import re
    title = re.search(r'og:title" content="([^"]*)"', h).group(1)
    desc = re.search(r'og:description" content="([^"]*)"', h).group(1)
    assert len(title) <= 61 and title.endswith("…")
    assert len(desc) <= 151 and desc.endswith("…")

def test_defaults_when_empty():
    h = render_share_html(**{**BASE, "title": "", "description": ""})
    assert "브리핑 코리아 · 정치 브리핑" in h

def test_redirect_in_js_and_noscript():
    h = render_share_html(**BASE)
    assert "location.replace(" in h
    assert "https://koreanpolitical.web.app/?issue=abc" in h  # JS 문자열
    assert '<noscript><a href="https://koreanpolitical.web.app/?issue=abc"' in h

def test_script_break_is_neutralized():
    evil = "https://x/?a=</script><script>evil()</script>"
    h = render_share_html(**{**BASE, "redirect_url": evil})
    # 원본 </script> 시퀀스가 그대로 들어가면 안 됨
    assert "</script><script>evil()" not in h
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd politics_backend && .venv/bin/pytest tests/test_share_render.py -v`
Expected: FAIL (`ModuleNotFoundError: utils.share_render`)

- [ ] **Step 3: Write minimal implementation**

```python
# politics_backend/utils/share_render.py
"""공유용 OG 카드 HTML을 만드는 순수 함수. Firestore/FastAPI 비의존."""
import html
import json

TITLE_MAX = 60
DESC_MAX = 150
DEFAULT_TITLE = "브리핑 코리아 · 정치 브리핑"
DEFAULT_DESC = "실시간 정치 뉴스와 1차 소스 맥락 — 브리핑 코리아"


def _clip(s: str, n: int) -> str:
    s = (s or "").strip()
    if len(s) <= n:
        return s
    return s[: n - 1].rstrip() + "…"


def _js_string(s: str) -> str:
    # <script> 안에서 안전한 JS 문자열 리터럴. </script> 및 < 차단.
    return json.dumps(s or "").replace("<", "\\u003c")


def render_share_html(*, title, description, image_url, share_url, redirect_url) -> str:
    t = html.escape(_clip(title, TITLE_MAX) or DEFAULT_TITLE)
    d = html.escape(_clip(description, DESC_MAX) or DEFAULT_DESC)
    img = html.escape(image_url or "")
    su = html.escape(share_url or "")
    ru_attr = html.escape(redirect_url or "")
    ru_js = _js_string(redirect_url)
    return (
        "<!DOCTYPE html><html lang=\"ko\"><head>"
        "<meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<meta property=\"og:type\" content=\"article\">"
        f"<meta property=\"og:title\" content=\"{t}\">"
        f"<meta property=\"og:description\" content=\"{d}\">"
        f"<meta property=\"og:image\" content=\"{img}\">"
        f"<meta property=\"og:url\" content=\"{su}\">"
        "<meta name=\"twitter:card\" content=\"summary_large_image\">"
        f"<meta name=\"twitter:title\" content=\"{t}\">"
        f"<meta name=\"twitter:description\" content=\"{d}\">"
        f"<meta name=\"twitter:image\" content=\"{img}\">"
        f"<title>{t}</title>"
        f"<script>location.replace({ru_js});</script>"
        "</head><body>"
        f"<noscript><a href=\"{ru_attr}\">브리핑 코리아에서 보기</a></noscript>"
        "</body></html>"
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd politics_backend && .venv/bin/pytest tests/test_share_render.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
cd politics_backend
git add utils/share_render.py tests/test_share_render.py
git commit -m "feat(share): pure OG card HTML renderer with escaping + clipping"
```

---

## Task 2: 공유 라우터 (`routers/share_router.py`) + 등록

**Files:**
- Create: `politics_backend/routers/share_router.py`
- Modify: `politics_backend/main.py` (라우터 등록)
- Test: `politics_backend/tests/test_share_router.py`

**Interfaces:**
- Consumes: `render_share_html` (Task 1).
- Produces: FastAPI 라우트 `GET /share/issue/{issue_id}`, `GET /share/article/{article_id}` → `HTMLResponse(200)`. 테스트 seam `_fetch_issue_meta(id)->dict|None`, `_fetch_article_meta(id)->dict|None`(반환 dict 키: `title`, `description`).

- [ ] **Step 1: Write the failing test**

```python
# politics_backend/tests/test_share_router.py
from fastapi import FastAPI
from fastapi.testclient import TestClient
import routers.share_router as sr

app = FastAPI()
app.include_router(sr.router)
client = TestClient(app)

def test_issue_share_renders_og(monkeypatch):
    monkeypatch.setattr(sr, "_fetch_issue_meta",
                        lambda i: {"title": "추경 처리", "description": "국회 통과"})
    r = client.get("/share/issue/abc")
    assert r.status_code == 200
    assert 'og:title" content="추경 처리"' in r.text
    assert "/?issue=abc" in r.text
    assert "s-maxage" in r.headers.get("cache-control", "")

def test_missing_issue_returns_default_og_200(monkeypatch):
    monkeypatch.setattr(sr, "_fetch_issue_meta", lambda i: None)
    r = client.get("/share/issue/nope")
    assert r.status_code == 200
    assert "브리핑 코리아 · 정치 브리핑" in r.text

def test_article_share_renders_og(monkeypatch):
    monkeypatch.setattr(sr, "_fetch_article_meta",
                        lambda i: {"title": "기사 제목", "description": "기사 요약"})
    r = client.get("/share/article/xy")
    assert r.status_code == 200
    assert 'og:title" content="기사 제목"' in r.text
    assert "/?article=xy" in r.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd politics_backend && .venv/bin/pytest tests/test_share_router.py -v`
Expected: FAIL (`ModuleNotFoundError: routers.share_router`)

- [ ] **Step 3: Write minimal implementation**

```python
# politics_backend/routers/share_router.py
"""이슈/기사 공유용 OG 카드 라우트. 크롤러엔 OG HTML(200), 사람은 JS로 SPA 이동."""
import os
import logging

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from utils.share_render import render_share_html

router = APIRouter()
log = logging.getLogger(__name__)

WEB_APP_URL = os.getenv("WEB_APP_URL", "https://koreanpolitical.web.app").rstrip("/")
SHARE_BASE_URL = os.getenv("SHARE_BASE_URL", "https://politicsbackend-ruby.vercel.app").rstrip("/")
OG_DEFAULT_IMAGE = os.getenv("OG_DEFAULT_IMAGE", f"{WEB_APP_URL}/og-default.png")
CACHE_CONTROL = "public, s-maxage=600, stale-while-revalidate=86400"


def _fetch_issue_meta(issue_id: str):
    """Firestore에서 이슈 제목/요약만 읽음(뷰카운트 등 부작용 없음)."""
    try:
        from firebase.firebase_config import db
        doc = db.collection("issues").document(issue_id).get()
        if not doc.exists:
            return None
        d = doc.to_dict()
        return {"title": d.get("title"), "description": d.get("summary") or d.get("description")}
    except Exception as e:  # noqa: BLE001
        log.warning("share issue fetch failed: %s", e)
        return None


def _fetch_article_meta(article_id: str):
    try:
        from firebase.firebase_config import db
        doc = db.collection("articles").document(article_id).get()
        if not doc.exists:
            return None
        d = doc.to_dict()
        return {"title": d.get("title"), "description": d.get("summary")}
    except Exception as e:  # noqa: BLE001
        log.warning("share article fetch failed: %s", e)
        return None


def _html(meta, share_url, redirect_url) -> HTMLResponse:
    meta = meta or {}
    body = render_share_html(
        title=meta.get("title") or "",
        description=meta.get("description") or "",
        image_url=OG_DEFAULT_IMAGE,
        share_url=share_url,
        redirect_url=redirect_url,
    )
    return HTMLResponse(content=body, status_code=200,
                        headers={"Cache-Control": CACHE_CONTROL})


@router.get("/share/issue/{issue_id}")
async def share_issue(issue_id: str):
    return _html(
        _fetch_issue_meta(issue_id),
        share_url=f"{SHARE_BASE_URL}/share/issue/{issue_id}",
        redirect_url=f"{WEB_APP_URL}/?issue={issue_id}",
    )


@router.get("/share/article/{article_id}")
async def share_article(article_id: str):
    return _html(
        _fetch_article_meta(article_id),
        share_url=f"{SHARE_BASE_URL}/share/article/{article_id}",
        redirect_url=f"{WEB_APP_URL}/?article={article_id}",
    )
```

- [ ] **Step 4: Register the router in `main.py`**

`main.py`의 라우터 등록 블록(현재 `app.include_router(...)` 들이 모인 곳, 대략 56~65행) 아래에 추가. 상단 import 그룹에도 `from routers import share_router` 추가.

```python
# main.py — import 그룹에 추가
from routers import share_router
# main.py — include_router 블록 끝에 추가 (prefix 없음: 최종 경로 /share/...)
app.include_router(share_router.router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd politics_backend && .venv/bin/pytest tests/test_share_router.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Run full backend suite (회귀 없음 확인)**

Run: `cd politics_backend && .venv/bin/pytest -q`
Expected: 기존 통과 테스트 + 신규 9개 모두 PASS

- [ ] **Step 7: Commit**

```bash
cd politics_backend
git add routers/share_router.py tests/test_share_router.py main.py
git commit -m "feat(share): /share/issue,/share/article OG routes (200 + JS redirect)"
```

---

## Task 3: 프론트 공유 URL 교체 + `?article=` 딥링크

**Files:**
- Modify: `politics_front/src/components/IssueDetail.jsx` (`handleShare`, 대략 97~99행)
- Modify: `politics_front/src/components/NewsReaderModal.jsx` (`share`, 대략 41~48행)
- Modify: `politics_front/src/App.jsx` (딥링크 useEffect 대략 158~168행 + reader 오픈)
- Create: `politics_front/src/config/share.js`

**Interfaces:**
- Consumes: 백엔드 `/share/issue/{id}`, `/share/article/{id}` (Task 2).
- Produces: 공유 시 `navigator.share`가 `${SHARE_BASE}/share/...` URL을 전달. `?article=<id>` 진입 시 해당 기사 리더 오픈.

- [ ] **Step 1: 공유 베이스 설정 파일 생성**

```javascript
// politics_front/src/config/share.js
// 공유 링크가 찍힐 베이스. env로 분리해 커스텀 도메인 교체를 쉽게.
export const SHARE_BASE =
  process.env.REACT_APP_SHARE_BASE_URL || 'https://politicsbackend-ruby.vercel.app';

export const issueShareUrl = (id) => `${SHARE_BASE}/share/issue/${id}`;
export const articleShareUrl = (id) => `${SHARE_BASE}/share/article/${id}`;
```

- [ ] **Step 2: `IssueDetail.jsx` 공유 URL 교체**

`handleShare`의 `url` 라인을 교체. 상단에 import 추가.

```javascript
// import 추가 (파일 상단 import 그룹)
import { issueShareUrl } from '../config/share';

// handleShare 내부: 기존
//   const url = `${window.location.origin}/?issue=${issueId}`;
// 교체
const url = issueShareUrl(issueId);
```

- [ ] **Step 3: `NewsReaderModal.jsx` 공유 URL 교체(원문 유출 차단)**

`share`의 `shareData`를 교체. 상단에 import 추가. (원문 열기 `openOriginal`은 그대로 둔다.)

```javascript
// import 추가
import { articleShareUrl } from '../config/share';

// share 내부: 기존
//   const shareData = { title: current.title, url: current.source_url || window.location.href };
// 교체 — 앱 딥링크로 공유(원문은 '원문 보기' 버튼으로만)
const shareUrl = current.id ? articleShareUrl(current.id) : window.location.href;
const shareData = { title: current.title, url: shareUrl };
// 클립보드 폴백도 shareUrl 사용
//   기존 clipboard.writeText(current.source_url) → clipboard.writeText(shareUrl)
```

클립보드 폴백 라인(`navigator.clipboard && current.source_url` 분기)도 `shareUrl` 기준으로 수정:

```javascript
} else if (navigator.clipboard) {
  await navigator.clipboard.writeText(shareUrl);
  toast.success('링크를 복사했어요');
}
```

- [ ] **Step 4: `App.jsx`에 `?article=` 딥링크 처리 추가**

기존 `?issue=` 처리 useEffect(대략 158~168행)에 기사 분기를 추가한다. 기사 리더는 `setReaderArticle(content)`로 열리므로(현재 파일 124행), 딥링크에서는 백엔드에서 기사 단건을 받아 열어야 한다. 기존 기사 fetch 훅/함수를 재사용한다.

```javascript
// 기존 useEffect 내부, iid 처리 아래에 추가
const aid = params.get('article');
if (aid) {
  setActiveTab('news');
  // 기사 단건 조회 후 리더 오픈 (백엔드 GET /api/news/{id})
  import('./api').then(async ({ getArticleById }) => {
    try {
      const article = await getArticleById(aid);
      if (article) setReaderArticle(article);
    } catch (_) { /* 없는 기사 무시 */ }
  });
}
```

> 참고: `getArticleById`가 `src/api.js`에 없으면 이 Step에서 함께 추가한다. 백엔드 라우트는 `GET /api/news/{article_id}` (news_router 102행)이며 응답은 `{success, data:{article}}` 형태다. 반환은 `res?.data?.article ?? null`.

`src/api.js`에 함수가 없을 경우 추가:

```javascript
// src/api.js
export async function getArticleById(articleId) {
  const res = await fetch(`${API_BASE}/api/news/${articleId}`);
  const json = await res.json();
  return json?.data?.article ?? null;
}
```

(`API_BASE`는 해당 파일의 기존 베이스 상수명을 따른다. 파일에서 확인해 동일 상수 사용.)

- [ ] **Step 5: 빌드로 검증(회귀 없음)**

Run: `cd politics_front && CI=false npm run build`
Expected: `Compiled successfully` (경고는 허용, 에러 없어야 함)

- [ ] **Step 6: Commit**

```bash
cd politics_front
git add src/config/share.js src/components/IssueDetail.jsx src/components/NewsReaderModal.jsx src/App.jsx src/api.js
git commit -m "feat(share): route share links through /share endpoint + ?article deep link"
```

---

## Task 4: 기본 OG 이미지 + 배포 + 실카드 검증

**Files:**
- Create: `politics_front/public/og-default.png` (1200×630 브랜드 이미지)

**Interfaces:**
- Consumes: Task 2·3 배포 결과.
- Produces: `koreanpolitical.web.app/og-default.png` 공개 서빙 + 실제 공유 카드 렌더.

- [ ] **Step 1: 기본 OG 이미지 배치**

1200×630 PNG를 `politics_front/public/og-default.png`에 둔다. 소스는 착수 시 사용자에게 확인(제공받거나 브랜드 톤 `#21808d` + "브리핑 코리아" 로고로 생성). 파일 존재 확인:

Run: `cd politics_front && file public/og-default.png`
Expected: `PNG image data, 1200 x 630`

- [ ] **Step 2: 백엔드 배포 (Vercel 프로덕션)**

`play_publish` 계정과 무관. 기존 배포 방식대로:

Run: `cd politics_backend && npx vercel --prod` (또는 저장소 연동 자동배포면 `git push`)
Expected: 배포 URL 반환. 배포 후 `curl -s https://politicsbackend-ruby.vercel.app/share/issue/<실제이슈id> | grep -o 'og:title[^>]*'` 로 실제 제목 확인.

- [ ] **Step 3: 프론트 배포 (Firebase Hosting)**

Run: `cd politics_front && CI=false npm run build && npx firebase deploy --only hosting`
Expected: 배포 완료. `curl -sI https://koreanpolitical.web.app/og-default.png` → `200` + `content-type: image/png`.

- [ ] **Step 4: 실제 크롤러 카드 검증**

- 카카오: https://developers.kakao.com/tool/debugger/sharing 에 `https://politicsbackend-ruby.vercel.app/share/issue/<id>` 입력 → 제목·설명·이미지 카드 확인.
- 페이스북: https://developers.facebook.com/tools/debug/ 에 같은 URL → OG 파싱 확인.
- 사람 흐름: 브라우저로 같은 URL 열기 → `koreanpolitical.web.app/?issue=<id>`로 이동해 이슈 상세가 열리는지 확인.
- 기사: `/share/article/<id>` 동일 검증 + `?article=<id>` 진입 시 리더 열림 확인.

- [ ] **Step 5: Commit**

```bash
cd politics_front
git add public/og-default.png
git commit -m "feat(share): brand default OG image 1200x630"
```

---

## Self-Review 결과

- **스펙 커버리지:** 동적 OG 카드(Task 1·2), 뉴스 원문 유출 차단(Task 3 Step 3), 기사 딥링크(Task 3 Step 4), 이슈 공유 카드화(Task 3 Step 2), 기본 이미지(Task 4), 에러 폴백(Task 2 `_html`+Task 1 기본값), 캐시 헤더(Task 2), env 분리(Global Constraints+Task 2·3) — 모두 태스크에 매핑됨.
- **범위 밖(스펙과 일치):** 카카오 SDK 배선, 안드로이드 App Links, 이슈별 동적 OG 이미지 — 이 계획에 없음(별도 사이클).
- **타입 일관성:** `_fetch_issue_meta`/`_fetch_article_meta` 반환 키 `title`/`description`가 `render_share_html` 인자와 일치. 프론트 `issueShareUrl`/`articleShareUrl`가 백엔드 경로와 일치.
- **열린 항목:** Task 4 Step 1 OG 이미지 소스(제작 vs 사용자 제공) — 착수 시 확정.
