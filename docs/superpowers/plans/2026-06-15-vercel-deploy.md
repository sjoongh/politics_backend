# Vercel 배포 (슬림 API + GitHub Actions 수집) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (inline). Steps use `- [ ]`.

**Goal:** FastAPI 백엔드의 읽기/인증 API를 Vercel(무료)에 배포하고, 서버리스에 안 맞는 뉴스 수집은 GitHub Actions 크론으로 분리한다.

**Architecture:** 수집 전용 무거운 라이브러리(`trafilatura`/`google.generativeai`/`feedparser`)를 **옵셔널 import**로 만들어 슬림 의존성만으로 앱이 부팅되게 한다. Vercel은 `requirements.txt`(슬림) + `api/index.py`(ASGI) + `vercel.json`. 수집은 `requirements-collect.txt`(풀 deps)로 GitHub Actions cron에서 실행.

**Tech Stack:** FastAPI, Vercel Python runtime, GitHub Actions. 검증: **슬림 deps만 깐 새 venv에서 `from main import app` 부팅** + pytest.

**전제:** Vercel 함수 크기 250MB(Hobby) — `lxml`(trafilatura)·`google-generativeai`·`openai` 제외하면 들어감. maxDuration Hobby 최대 60초(읽기 API는 <2초라 무관).

작업 전 `git checkout -b feat/vercel`. `.venv`(기존)는 풀 deps. 슬림 검증용으로 별도 venv 생성.

---

## Task 1: 수집 전용 라이브러리 옵셔널 import

**Files:** Modify `services/ai_service.py`, `utils/article_fetch.py`, `services/news_service.py`

- [ ] **Step 1: `utils/article_fetch.py`** — `import trafilatura`를 옵셔널로:
```python
"""기사 본문 크롤링 유틸 (trafilatura 기반, 옵셔널)."""
try:
    import trafilatura
except ImportError:
    trafilatura = None


def fetch_article_text(url: str, min_len: int = 200) -> str:
    if not url or trafilatura is None:
        return ""
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return ""
        text = trafilatura.extract(downloaded, include_comments=False, include_tables=False) or ""
        text = text.strip()
        return text if len(text) >= min_len else ""
    except Exception:
        return ""
```

- [ ] **Step 2: `services/ai_service.py`** — `import google.generativeai as genai`를 옵셔널로(2행 교체):
```python
try:
    import google.generativeai as genai
except ImportError:
    genai = None
```
그리고 `__init__` 교체:
```python
    def __init__(self):
        if genai is not None:
            genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
            self.model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
            self.model = genai.GenerativeModel(self.model_name)
        else:
            self.model_name = None
            self.model = None
```
그리고 `summarize_by_category2`의 `try:` 바로 다음 줄에 가드 추가:
```python
        if self.model is None:
            return {"success": False, "message": "AI 비활성(google-generativeai 미설치)"}
```
(그리고 `_generate_comprehensive_summary`도 동일 가드: 함수 `try:` 다음에 `if self.model is None: return "AI 비활성"`.)

- [ ] **Step 3: `services/news_service.py`** — `import feedparser`(2행) 옵셔널로:
```python
try:
    import feedparser
except ImportError:
    feedparser = None
```
그리고 `collect_news_from_rss`의 `try:` 다음 줄에 가드:
```python
            if feedparser is None:
                return {"success": False, "message": "수집 비활성(feedparser 미설치). 수집은 GitHub Actions에서 실행."}
```

- [ ] **Step 4: 풀 deps 환경에서 회귀 없는지** — `source .venv/bin/activate && python3 -m py_compile services/ai_service.py services/news_service.py utils/article_fetch.py && python -m pytest tests/ -q` → 모두 통과(33+).

- [ ] **Step 5: 슬림 부팅 검증 (핵심)** — 새 venv에 슬림 deps만 깔고 `from main import app` 부팅:
```bash
cd /Users/manager/side/politics_backend
python3.11 -m venv /tmp/slimvenv && source /tmp/slimvenv/bin/activate
pip install -q fastapi firebase-admin google-cloud-firestore "python-jose[cryptography]" "passlib[bcrypt]" bcrypt==4.0.1 "pydantic[email]" requests python-dotenv python-multipart python-dateutil httpx
python -c "from main import app; print('✓ 슬림 부팅 OK, 라우트:', len(app.routes))"
deactivate
```
Expected: `✓ 슬림 부팅 OK, 라우트: N` (ImportError 없이). 실패하면 누락 import를 추가 옵셔널화.

- [ ] **Step 6: Commit**
```bash
git add services/ai_service.py services/news_service.py utils/article_fetch.py
git commit -m "feat(vercel): make collection-only libs optional (boots without trafilatura/genai/feedparser)"
```

---

## Task 2: requirements 분리 (슬림 + 수집)

**Files:** Modify `requirements.txt`, Create `requirements-collect.txt`

- [ ] **Step 1: `requirements.txt`를 슬림으로 교체** (Vercel·API 전용):
```
# API 런타임(슬림) — Vercel 배포용. 수집 라이브러리는 requirements-collect.txt
fastapi>=0.104.1
firebase-admin>=6.8.0
google-cloud-firestore>=2.16.0
requests>=2.31.0
httpx>=0.27.0
python-dotenv>=1.0.0
python-jose[cryptography]>=3.3.0
passlib[bcrypt]>=1.7.4
bcrypt==4.0.1
pydantic[email]>=2.8.2
python-multipart>=0.0.6
python-dateutil>=2.9.0.post0
```

- [ ] **Step 2: `requirements-collect.txt` 생성** (로컬·GitHub Actions용 = 슬림 + 수집/서버):
```
-r requirements.txt

# 로컬 실행 서버
uvicorn[standard]>=0.24.0

# 수집/AI 전용 (Vercel 배포에서는 제외 — 용량/서버리스)
google-generativeai>=0.8.3
openai>=1.3.5
feedparser>=6.0.11
beautifulsoup4>=4.12.0
trafilatura>=1.8.0
schedule>=1.2.0
```

- [ ] **Step 3: 로컬 .venv에 수집 deps 유지 확인** — `source .venv/bin/activate && python -c "import trafilatura, feedparser, google.generativeai; print('수집 deps ok')"`. (이미 깔려있으면 OK)

- [ ] **Step 4: Commit**
```bash
git add requirements.txt requirements-collect.txt
git commit -m "feat(vercel): split slim requirements (API) vs requirements-collect (collection)"
```

---

## Task 3: Vercel 엔트리 + 설정

**Files:** Create `api/index.py`, `vercel.json`

- [ ] **Step 1: `api/index.py`** (ASGI app 노출):
```python
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app  # noqa: E402  (FastAPI ASGI app)
```

- [ ] **Step 2: `vercel.json`** (모든 경로를 함수로):
```json
{
  "version": 2,
  "functions": {
    "api/index.py": { "runtime": "@vercel/python@4.3.0", "maxDuration": 60 }
  },
  "rewrites": [
    { "source": "/(.*)", "destination": "/api/index" }
  ]
}
```

- [ ] **Step 3: Python 버전 고정** — `runtime.txt` 생성: `python-3.11`. (Vercel이 인식)

- [ ] **Step 4: 문법 확인** — `python3 -m py_compile api/index.py && echo ok`. (실제 배포는 사용자 Vercel에서)

- [ ] **Step 5: Commit**
```bash
git add api/index.py vercel.json runtime.txt
git commit -m "feat(vercel): ASGI entry (api/index.py) + vercel.json + python pin"
```

---

## Task 4: GitHub Actions 수집 크론

**Files:** Create `.github/workflows/collect.yml`

- [ ] **Step 1: `.github/workflows/collect.yml`**
```yaml
name: News Collect
on:
  schedule:
    - cron: "0 * * * *"   # 매시 정각(UTC)
  workflow_dispatch: {}
jobs:
  collect:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r requirements-collect.txt
      - name: Run collection
        env:
          FIREBASE_TYPE: ${{ secrets.FIREBASE_TYPE }}
          FIREBASE_PROJECT_ID: ${{ secrets.FIREBASE_PROJECT_ID }}
          FIREBASE_PRIVATE_KEY_ID: ${{ secrets.FIREBASE_PRIVATE_KEY_ID }}
          FIREBASE_PRIVATE_KEY: ${{ secrets.FIREBASE_PRIVATE_KEY }}
          FIREBASE_CLIENT_EMAIL: ${{ secrets.FIREBASE_CLIENT_EMAIL }}
          FIREBASE_CLIENT_ID: ${{ secrets.FIREBASE_CLIENT_ID }}
          FIREBASE_AUTH_URI: ${{ secrets.FIREBASE_AUTH_URI }}
          FIREBASE_TOKEN_URI: ${{ secrets.FIREBASE_TOKEN_URI }}
          FIREBASE_AUTH_PROVIDER_X509_CERT_URL: ${{ secrets.FIREBASE_AUTH_PROVIDER_X509_CERT_URL }}
          FIREBASE_CLIENT_X509_CERT_URL: ${{ secrets.FIREBASE_CLIENT_X509_CERT_URL }}
          GOOGLE_API_KEY: ${{ secrets.GOOGLE_API_KEY }}
          AI_THROTTLE_SEC: "2"
        run: |
          python -c "import asyncio; from services.news_service import news_service; print(asyncio.run(news_service.collect_news_from_rss()).get('message'))"
```

- [ ] **Step 2: Commit**
```bash
git add .github/workflows/collect.yml
git commit -m "feat(vercel): GitHub Actions hourly news collection (full deps + firebase secrets)"
```
> 사용자: GitHub 레포 Settings → Secrets에 위 `FIREBASE_*` + `GOOGLE_API_KEY` 등록(.env 값). 의원 동기화(`assembly`)도 같은 패턴으로 워크플로 추가 가능.

---

## Task 5: 배포 가이드 문서

**Files:** Create `docs/DEPLOY_VERCEL.md`

- [ ] **Step 1: `docs/DEPLOY_VERCEL.md`** 작성 (요지):
```markdown
# Vercel 배포 가이드

## 1. Vercel에 레포 연결
Vercel → New Project → `sjoongh/politics_backend` import. 프레임워크 프리셋: Other.
- `vercel.json`/`api/index.py`/`requirements.txt`(슬림) 자동 인식.

## 2. 환경변수 (Vercel Project Settings → Environment Variables)
FIREBASE_TYPE, FIREBASE_PROJECT_ID, FIREBASE_PRIVATE_KEY_ID, FIREBASE_PRIVATE_KEY,
FIREBASE_CLIENT_EMAIL, FIREBASE_CLIENT_ID, FIREBASE_AUTH_URI, FIREBASE_TOKEN_URI,
FIREBASE_AUTH_PROVIDER_X509_CERT_URL, FIREBASE_CLIENT_X509_CERT_URL,
ADMIN_KEY, ASSEMBLY_API_KEY, SECRET_KEY  (값은 politics_backend/.env 참고)
(GOOGLE_API_KEY는 수집이 GitHub Actions라 Vercel엔 불필요)

## 3. 배포 & 검증
- Deploy → `https://<project>.vercel.app/health` → 200
- `https://<project>.vercel.app/api/issues` → 이슈 목록

## 4. 수집(GitHub Actions)
레포 Secrets에 FIREBASE_* + GOOGLE_API_KEY 등록 → `.github/workflows/collect.yml`가 매시 실행.

## 5. 프론트 연결
배포 URL을 `politics_front/src/hooks/api.js` 프로덕션 baseURL로 교체 → web 재배포.
```

- [ ] **Step 2: Commit**
```bash
git add docs/DEPLOY_VERCEL.md
git commit -m "docs: Vercel deploy guide"
```

---

## Task 6: (배포 후) 프론트 URL 연결
- [ ] 사용자가 Vercel 배포 → `*.vercel.app` URL 확보.
- [ ] `politics_front/src/hooks/api.js` 프로덕션 baseURL을 그 URL로 교체 → 커밋·push → `firebase deploy`.
(URL 나오면 이 단계는 즉시 처리)

---

## Self-Review
- 스펙 커버리지: 옵셔널 import(T1)·requirements 분리(T2)·Vercel 엔트리(T3)·수집 크론(T4)·문서(T5)·프론트연결(T6).
- 핵심 검증: **슬림 venv 부팅**(T1-S5)으로 Vercel 환경 재현. pytest 회귀.
- 타입 일관성: 옵셔널 가드는 기존 반환형({success,message}) 유지. 수집/AI는 라이브러리 없으면 graceful 실패.
- 한계: 실제 Vercel 배포·GH Actions 실행은 사용자 계정/시크릿 필요. 코드/부팅은 로컬 검증.

## 다음
배포 후 프론트 URL 연결 + (선택) 의원 동기화 워크플로 + 커스텀 도메인(앱 재배포 영구 회피).
