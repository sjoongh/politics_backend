# Cloud Run 배포 가이드

백엔드를 Google Cloud Run에 배포한다. Firestore와 같은 프로젝트(`koreanpolitical`)라
**런타임 서비스계정(ADC)로 자동 인증** → `FIREBASE_*` 키를 환경변수에 넣지 않아도 된다.
(`firebase/firebase_config.py`가 키 env 없으면 ADC로 폴백)

## 사전 준비 (레포에 포함됨)
- `Dockerfile` — python:3.11-slim, `python run_server.py`로 기동 ($PORT 사용)
- `.dockerignore` — `.env`/키파일/`.venv` 등 제외 (이미지에 비밀 안 들어감)

## 콘솔에서 배포 (gcloud 없이)
1. GCP 콘솔 → **Cloud Run** → **"서비스 만들기"**
2. **"저장소에서 지속적으로 배포"** 선택 → **Cloud Build 설정**
   - GitHub 연결 → 저장소 `sjoongh/politics_backend`, 브랜치 `main`
   - **빌드 유형: Dockerfile** (경로 `/Dockerfile`)
3. 서비스 설정:
   - 리전: **asia-northeast3 (서울)**
   - 인증: **미인증 호출 허용** (공개 API)
   - 컨테이너 포트: **8080**
4. **보안 → 서비스 계정**: **`firebase-adminsdk-1h5rn@koreanpolitical.iam.gserviceaccount.com`** 선택
   - (이 계정이 Firestore 접근 권한 보유 → ADC로 키 없이 동작)
   - 또는 런타임 SA에 `roles/datastore.user` 부여
5. **변수 및 보안 비밀** (env) — FIREBASE_* 는 불필요. 아래만:
   - `ADMIN_KEY` = (관리자 엔드포인트 보호용 임의 문자열)
   - `GOOGLE_API_KEY` = (Gemini 키 — 수집/AI 쓸 때)
   - `AI_THROTTLE_SEC` = `2` (선택)
6. **만들기/배포** → 빌드·배포 완료되면 **서비스 URL**(`https://politics-backend-XXXX.a.run.app`) 생성

## 배포 후
- 검증: `curl https://<URL>/health` → 200, `curl https://<URL>/api/issues` → 이슈 2건
- **이 URL을 프론트에 반영** (`politics_front/src/hooks/api.js`의 프로덕션 baseURL) → 프론트 재배포
  (URL 주시면 대신 바꿔 드림)

## 정기 수집 (선택)
Cloud Scheduler가 `POST /api/news/collect` 를 `X-Admin-Key` 헤더로 주기 호출. (docs/scheduler.md)

## 참고
- 로컬 개발은 기존대로 `.env`(서비스계정 키)로 동작 — 키 있으면 인증서, 없으면 ADC.
- 무료 한도(월 200만 요청·scale-to-zero)면 개인 앱은 사실상 무료. 콜드스타트 1~3초.
