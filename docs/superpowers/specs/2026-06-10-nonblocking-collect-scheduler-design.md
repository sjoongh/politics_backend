# 비차단 수집 + Cloud Scheduler 배치 (Design Spec)

작성일: 2026-06-10
대상: politics_backend (원본). 현재 수집은 동기 블로킹 + 스케줄러 없음 → 비차단화 + 외부 크론.

## 1. 현황 문제
- `POST /api/news/collect`가 수집을 **동기 HTTP 요청 안에서** 실행 → `time.sleep(3)`(이벤트루프 블로킹) + 기사당 `asyncio.sleep(15)` → 수 분 소요 → **타임아웃 + 서버 멈춤**.
- 트리거에 **인증 없음**(admin 체크 주석처리).
- **스케줄러/배치 전혀 없음**(`schedule` 라이브러리 미사용).

## 2. 목표 & 범위
- 수집을 **비차단**으로(즉시 응답, 백그라운드 실행), 트리거에 **X-Admin-Key**.
- 정기 실행은 **Cloud Scheduler**가 `/collect`를 주기 호출(코드 아님, 문서로).
- **제외:** 정교한 작업 큐(Cloud Tasks), 수집 로직 자체 재작성(요약 엔진 교체 등).

## 3. 코드 변경
### a. `services/news_service.py`
- 블로킹 `time.sleep(self.request_delay)` → `await asyncio.sleep(self.request_delay)`.
- 기사당 AI 쓰로틀 `await asyncio.sleep(15)` → `await asyncio.sleep(AI_THROTTLE_SEC)` (env `AI_THROTTLE_SEC`, 기본 2.0). 이벤트루프 비차단 유지.

### b. `routers/news_router.py`
- `POST /api/news/collect(background_tasks: BackgroundTasks, x_admin_key: Header)`:
  - `_require_admin(x_admin_key)` (env `ADMIN_KEY`, 미설정/불일치 시 401, fail-closed).
  - `background_tasks.add_task(news_service.collect_news_from_rss)` 던지고 **즉시 `{success, message:"수집을 시작했습니다."}`** 반환.

## 4. 배치 (인프라 — 문서 `docs/scheduler.md`)
- Cloud Scheduler HTTP 잡: 주기(예: `0 * * * *`)마다 `POST {SERVICE_URL}/api/news/collect`, 헤더 `X-Admin-Key: $ADMIN_KEY`.
- gcloud 예시 명령 제공.
- ⚠️ Cloud Run: BackgroundTask는 응답 후 실행 → 인스턴스 다운 시 잘릴 수 있음. **`--no-cpu-throttling`(CPU always allocated) 또는 `--min-instances=1`** 권장. 문서에 명시.

## 5. 검증
- Firebase/Gemini 키 없어 실행 불가 → `py_compile` 문법 + 코드리뷰.
- 가능한 순수 로직(throttle env 파싱 등)은 분리해 pytest(이미 .venv 있음).

## 6. 성공 기준
- `/collect`가 즉시 응답(비차단), admin 키로 보호.
- 수집 중 이벤트루프 블로킹 없음(`time.sleep` 제거).
- Cloud Scheduler 설정 문서로 자동 주기 수집 가능.

## 7. 후속
요약 엔진/쓰로틀 최적화, Cloud Tasks 기반 견고한 작업 큐, 수집 실패 알림.
