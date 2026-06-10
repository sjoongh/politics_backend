# 비차단 수집 + Cloud Scheduler 배치 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/api/news/collect`를 비차단(BackgroundTask 즉시 응답)+admin키 보호로 바꾸고, 수집 로직의 블로킹 sleep을 제거하며, Cloud Scheduler 배치 설정을 문서화한다.

**Architecture:** 원본 플랫 구조. 수집 로직(`news_service`)의 블로킹 `time.sleep` → `await asyncio.sleep`, AI 쓰로틀은 env 설정. 라우터의 `/collect`는 `BackgroundTasks`로 즉시 응답 + `X-Admin-Key`. 배치는 Cloud Scheduler(인프라, 문서).

**Tech Stack:** FastAPI, asyncio, google-cloud-firestore(원본). 검증: py_compile + 일부 pure 로직 pytest(.venv 기존).

**검증:** Firebase/Gemini 키 없어 실행 불가 → `py_compile` + 리뷰. throttle env 파싱은 순수 함수로 빼서 pytest. 작업 전 `git checkout -b feat/nonblocking-collect`. 작업 디렉토리 `/Users/manager/side/politics_backend`.

---

## 기존 코드(참고)
- `services/news_service.py`: `import time`(L3), `import asyncio`(L11), `self.request_delay = 3`(L37), `await asyncio.sleep(15)`(L179), `time.sleep(self.request_delay)`(L278). 싱글턴 `news_service`. (`import os` 없음 → 추가 필요)
- `routers/news_router.py`: `POST /collect`가 `return await news_service.collect_news_from_rss()` (동기 대기). `from fastapi import HTTPException, APIRouter, status, Depends`.
- `utils/member_rules.py`(앞 작업): pure 로직 + pytest 패턴 참고. `.venv` 존재(pytest 설치됨).

## 파일 구조
| 파일 | 변경 |
|------|------|
| `utils/collect_config.py` | (신규) `ai_throttle_seconds()` 순수 env 파서 |
| `tests/test_collect_config.py` | (신규) pytest |
| `services/news_service.py` | 블로킹 sleep 제거 + throttle env |
| `routers/news_router.py` | /collect → BackgroundTasks + X-Admin-Key |
| `docs/scheduler.md` | Cloud Scheduler 설정 문서 |

---

## Task 1: throttle 설정 순수 함수 + 테스트

**Files:** Create `utils/collect_config.py`, `tests/test_collect_config.py`

- [ ] **Step 1: 실패 테스트 `tests/test_collect_config.py`**
```python
import os
from utils.collect_config import ai_throttle_seconds


def test_default_when_unset(monkeypatch):
    monkeypatch.delenv("AI_THROTTLE_SEC", raising=False)
    assert ai_throttle_seconds() == 2.0


def test_reads_env(monkeypatch):
    monkeypatch.setenv("AI_THROTTLE_SEC", "0.5")
    assert ai_throttle_seconds() == 0.5


def test_invalid_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("AI_THROTTLE_SEC", "abc")
    assert ai_throttle_seconds() == 2.0


def test_negative_clamped_to_zero(monkeypatch):
    monkeypatch.setenv("AI_THROTTLE_SEC", "-3")
    assert ai_throttle_seconds() == 0.0
```

- [ ] **Step 2: 실패 확인** — Run: `cd /Users/manager/side/politics_backend && source .venv/bin/activate && python -m pytest tests/test_collect_config.py -v` → FAIL.

- [ ] **Step 3: `utils/collect_config.py` 구현** (firebase 비의존)
```python
"""수집 관련 설정 순수 함수 (firebase 비의존, 테스트 대상)."""
import os

DEFAULT_AI_THROTTLE = 2.0


def ai_throttle_seconds() -> float:
    """기사당 AI 호출 간 대기(초). env AI_THROTTLE_SEC, 기본 2.0, 음수는 0으로."""
    raw = os.getenv("AI_THROTTLE_SEC")
    if raw is None:
        return DEFAULT_AI_THROTTLE
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_AI_THROTTLE
    return max(0.0, val)
```

- [ ] **Step 4: 통과 확인** — Run: `source .venv/bin/activate && python -m pytest tests/test_collect_config.py -v` → 4 passed.

- [ ] **Step 5: Commit**
```bash
git add utils/collect_config.py tests/test_collect_config.py
git commit -m "feat(collect): ai_throttle_seconds env parser + tests"
```

---

## Task 2: news_service 블로킹 sleep 제거 + throttle env

**Files:** Modify `services/news_service.py`. (firebase 의존 → py_compile만.)

- [ ] **Step 1: import 추가** — `services/news_service.py` 상단(예: `import asyncio` 다음 줄)에 추가:
```python
from utils.collect_config import ai_throttle_seconds
```

- [ ] **Step 2: 기사당 AI 쓰로틀을 env 기반으로** — `await asyncio.sleep(15)` 한 줄을 다음으로 교체:
```python
                            await asyncio.sleep(ai_throttle_seconds())
```
(들여쓰기는 원래 그 줄과 동일하게 유지 — 28칸.)

- [ ] **Step 3: 블로킹 sleep 제거** — `time.sleep(self.request_delay)` 한 줄을 다음으로 교체(이벤트루프 비차단):
```python
                        await asyncio.sleep(self.request_delay)
```
(들여쓰기 24칸, 원래 줄과 동일.)

- [ ] **Step 4: 문법 검증** — Run: `cd /Users/manager/side/politics_backend && python3 -m py_compile services/news_service.py && echo "✓ syntax ok"`. 그리고 잔존 블로킹 확인: `grep -n "time.sleep" services/news_service.py` → **결과 없어야 함**(다른 time.sleep 없음 확인). `import time`은 미사용이면 남겨둬도 무방(원본 유지).

- [ ] **Step 5: Commit**
```bash
git add services/news_service.py
git commit -m "fix(collect): remove blocking time.sleep, configurable AI throttle (non-blocking)"
```

---

## Task 3: /collect 비차단(BackgroundTasks) + X-Admin-Key

**Files:** Modify `routers/news_router.py`. (py_compile만.)

- [ ] **Step 1: import 보강** — `routers/news_router.py` 상단 import를 다음으로(BackgroundTasks, Header, os 추가):
```python
import os
from fastapi import HTTPException, APIRouter, status, Depends, BackgroundTasks, Header
from typing import Dict, Any, Optional
```
(기존 `from fastapi import HTTPException, APIRouter, status, Depends`와 `from typing import ...`를 위로 교체. `auth_service`, `ResponseModel`, `news_service` import는 그대로 유지.)

- [ ] **Step 2: admin 가드 헬퍼 추가** — `router = APIRouter()` 다음에 추가:
```python
def _require_admin(x_admin_key: Optional[str]):
    expected = os.getenv("ADMIN_KEY")
    if not expected or x_admin_key != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="관리자 권한이 필요합니다.")
```

- [ ] **Step 3: `/collect` 엔드포인트 교체** — 기존 `collect_news` 함수 전체(데코레이터 포함)를 다음으로 교체:
```python
@router.post("/collect", response_model=ResponseModel)
async def collect_news(
    background_tasks: BackgroundTasks,
    x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key"),
):
    """뉴스 수집을 백그라운드로 시작(비차단). 관리자 키 필요."""
    _require_admin(x_admin_key)
    background_tasks.add_task(news_service.collect_news_from_rss)
    return {"success": True, "message": "뉴스 수집을 시작했습니다.", "data": {"status": "started"}}
```

- [ ] **Step 4: 문법 검증** — Run: `cd /Users/manager/side/politics_backend && python3 -m py_compile routers/news_router.py main.py && echo "✓ syntax ok"`. 확인: `grep -n "BackgroundTasks\|_require_admin\|add_task" routers/news_router.py`.

- [ ] **Step 5: Commit**
```bash
git add routers/news_router.py
git commit -m "feat(collect): /api/news/collect non-blocking (BackgroundTasks) + X-Admin-Key"
```

---

## Task 4: Cloud Scheduler 문서 + 전체 검증

**Files:** Create `docs/scheduler.md`

- [ ] **Step 1: `docs/scheduler.md` 작성**
```markdown
# 정기 뉴스 수집 (Cloud Scheduler)

`POST /api/news/collect` 은 비차단(즉시 응답, 백그라운드 수집)이며 `X-Admin-Key` 헤더가 필요하다.
Cloud Scheduler 가 주기적으로 이 엔드포인트를 호출하게 한다.

## 환경변수
- `ADMIN_KEY`: 수집 트리거 보호 키 (Cloud Run 서비스 + Scheduler 양쪽 동일 값)
- `AI_THROTTLE_SEC`: 기사당 AI 호출 간 대기(초). 기본 2.0. (Gemini 무료 쿼터에 맞춰 조정)

## Cloud Scheduler 작업 생성 (예: 매시 정각)
```
gcloud scheduler jobs create http news-collect \
  --schedule="0 * * * *" \
  --uri="https://<SERVICE_URL>/api/news/collect" \
  --http-method=POST \
  --headers="X-Admin-Key=<ADMIN_KEY 값>" \
  --location=asia-northeast3
```

## Cloud Run 주의 (중요)
BackgroundTask 는 HTTP 응답을 보낸 뒤 실행된다. Cloud Run 이 요청 후 인스턴스를 내리면 수집이 중간에 끊길 수 있다.
다음 중 하나로 백그라운드 실행을 보장한다:
- `gcloud run services update <SVC> --no-cpu-throttling` (CPU 항상 할당), 또는
- `--min-instances=1` 로 인스턴스 상시 유지.

수집이 매우 길면(피드/기사 많음) 향후 Cloud Tasks 기반 작업 큐로 분리 권장.
```

- [ ] **Step 2: 전체 문법 + 테스트** — Run:
```bash
cd /Users/manager/side/politics_backend && source .venv/bin/activate
python3 -m py_compile services/news_service.py routers/news_router.py main.py utils/collect_config.py && echo "✓ syntax ok"
python -m pytest tests/test_collect_config.py tests/test_member_rules.py tests/test_member_models.py -q
```
Expected: `✓ syntax ok` 그리고 11 passed (collect 4 + member 7).

- [ ] **Step 3: Commit**
```bash
git add docs/scheduler.md
git commit -m "docs: Cloud Scheduler setup for periodic news collection"
```

---

## Self-Review 메모 (플랜 작성자)
- 스펙 커버리지: 비차단(T3 BackgroundTasks), 블로킹 제거(T2), admin키(T3), throttle env(T1/T2), Cloud Scheduler 문서+Cloud Run 주의(T4). 전부.
- 플레이스홀더 없음.
- 타입 일관성: `ai_throttle_seconds()` T1 정의 → T2 사용. `_require_admin` T3 내부. BackgroundTasks add_task(news_service.collect_news_from_rss).
- 검증 한계: service/router는 py_compile, throttle 순수함수만 pytest(4).

## 다음 단계
요약 엔진/쿼터 최적화, Cloud Tasks 견고화, 이슈 추적 원본 이식, 프론트 의원 UI → 별도.
