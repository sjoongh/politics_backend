# Render 배포 / 복구 런북

프론트(`politics_front`)의 프로덕션 API URL = `https://politics-backend-9vp2.onrender.com`
이 백엔드는 Render의 GitHub 연동으로 `main` 푸시 시 자동 재배포된다.

## 1. 서비스 정지 해제
Render 대시보드 → `politics-backend` 서비스 → 정지(suspend) 상태면 **Resume**.
"suspended by its owner"가 결제/무료플랜 문제면 그 사유부터 해결.

## 2. 빌드/실행 설정 (서비스 Settings)
- Build Command: `pip install -r requirements.txt`
- Start Command: `python run_server.py`  (또는 `uvicorn main:app --host 0.0.0.0 --port $PORT`)
- Health Check Path: `/health`

## 3. 환경변수 (Environment)
새 Firebase 키 값으로 설정한다. (로컬 `politics_backend/.env`에 동일 값 있음 — 거기서 복사)

| 변수 | 값 |
|------|----|
| FIREBASE_TYPE | service_account |
| FIREBASE_PROJECT_ID | koreanpolitical |
| FIREBASE_PRIVATE_KEY_ID | 새 키 ID (12f06af51e0c2d8a244de5467461c9ae9c493dab) |
| FIREBASE_PRIVATE_KEY | 새 키 private_key 값, `\n` 포함 한 줄로 |
| FIREBASE_CLIENT_EMAIL | firebase-adminsdk-1h5rn@koreanpolitical.iam.gserviceaccount.com |
| FIREBASE_CLIENT_ID | JSON의 client_id |
| FIREBASE_AUTH_URI | https://accounts.google.com/o/oauth2/auth |
| FIREBASE_TOKEN_URI | https://oauth2.googleapis.com/token |
| FIREBASE_AUTH_PROVIDER_X509_CERT_URL | https://www.googleapis.com/oauth2/v1/certs |
| FIREBASE_CLIENT_X509_CERT_URL | JSON의 client_x509_cert_url |
| ADMIN_KEY | 관리자 엔드포인트 보호용 임의 문자열 |
| GOOGLE_API_KEY | Gemini 키 (수집/AI 쓸 때) |
| AI_THROTTLE_SEC | 2 |

⚠️ `FIREBASE_PRIVATE_KEY`는 한 줄로 `\n` 포함해 붙여넣기 (코드가 실제 줄바꿈으로 변환).
🔒 가능하면 키는 Render의 Secret 기능으로 관리.

## 4. 배포 & 검증
- `main` 푸시 시 자동 배포(또는 Manual Deploy).
- 검증:
  - `curl https://politics-backend-9vp2.onrender.com/health` → 200
  - `curl https://politics-backend-9vp2.onrender.com/api/issues` → 시드된 이슈 2건
  - 프론트(koreanpolitical.web.app) 새로고침 → 데이터 로드 확인

## 5. (선택) 정기 수집
Render Cron Job 또는 외부 스케줄러가 주기적으로
`POST /api/news/collect` 를 헤더 `X-Admin-Key: <ADMIN_KEY>` 와 호출. (`docs/scheduler.md` 참고)
