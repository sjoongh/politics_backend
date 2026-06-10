# 정기 뉴스 수집 (Cloud Scheduler)

`POST /api/news/collect` 은 비차단(즉시 응답, 백그라운드 수집)이며 `X-Admin-Key` 헤더가 필요하다.
Cloud Scheduler 가 주기적으로 이 엔드포인트를 호출하게 한다.

## 환경변수
- `ADMIN_KEY`: 수집 트리거 보호 키 (Cloud Run 서비스 + Scheduler 양쪽 동일 값)
- `AI_THROTTLE_SEC`: 기사당 AI 호출 간 대기(초). 기본 2.0. (Gemini 무료 쿼터에 맞춰 조정)

## Cloud Scheduler 작업 생성 (예: 매시 정각)
```bash
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
