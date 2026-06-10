# 라이브 앱 복구 (Render 백엔드) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline) to implement code tasks. Infra tasks (Task 4) are a runbook executed by the user in the Render dashboard. Steps use checkbox (`- [ ]`).

**Goal:** 새 Firebase 키로 백엔드를 Render에 다시 띄워, 프론트 라이브 앱(뉴스·이슈·의원·로그인)이 정상 동작하게 한다.

**Architecture:** 코드 쪽은 배포 준비(CORS 정상화 + Procfile + 배포 문서) 후 **로컬에서 전체 서버를 실제 Firestore(새 키)로 기동·스모크테스트**해 배포 동작을 사전 증명한다. 인프라 쪽은 Render 서비스 정지 해제 + 환경변수(새 키) 설정 + GitHub 자동배포(런북, 사용자 실행).

**Tech Stack:** FastAPI/uvicorn, firebase-admin, Render(호스팅, GitHub 연동 자동배포), 기존 `.venv`.

**검증:** 로컬 풀부팅 + 모든 엔드포인트 curl(실 Firestore). 작업 디렉토리 `/Users/manager/side/politics_backend`. 코드 작업 전 `git checkout -b fix/deploy-ready`.

---

## 배경 (현재 상태)
- 프론트(`politics_front/src/hooks/api.js`)의 프로덕션 API = `https://politics-backend-9vp2.onrender.com` (Render).
- Render 서비스가 **503 "suspended by its owner"** → 라이브 앱이 백엔드에 전혀 접속 못 함.
- 노출 키는 폐기, 새 키(`12f06af51e…`)는 로컬 `.env`에 있고 Firestore 연결 검증됨.
- `run_server.py`가 `uvicorn.run("main:app", host=0.0.0.0, port=int(os.getenv("PORT","8000")))` → Render의 `$PORT` 그대로 사용 가능.
- requirements.txt 에 fastapi/uvicorn/firebase-admin 등 모두 포함.

## 파일
| 파일 | 변경 |
|------|------|
| `main.py` | CORS 조합 정상화 |
| `Procfile` | (신규) Render start 명령 |
| `docs/DEPLOY.md` | (신규) Render 복구 런북 + env 목록 |

---

## Task 1: CORS 정상화 (코드)

**문제:** `allow_origins=["*"]` + `allow_credentials=True` 는 브라우저가 거부하는 조합. 프론트는 쿠키 자격증명을 안 쓰므로 `allow_credentials=False`로 두면 `["*"]`가 유효해진다.

**Files:** Modify `main.py`

- [ ] **Step 1:** `main.py`의 CORS 미들웨어에서 `allow_credentials=True,` → `allow_credentials=False,` 로 변경. (`allow_origins=["*"]` 유지 — 모바일(Capacitor)·웹 모든 오리진 허용, 자격증명 미사용이라 안전)

- [ ] **Step 2:** 문법 확인 — Run: `python3 -m py_compile main.py && echo ok`

- [ ] **Step 3:** Commit
```bash
git add main.py
git commit -m "fix(cors): allow_credentials=False so wildcard origin is valid"
```

---

## Task 2: Procfile + 배포 문서

**Files:** Create `Procfile`, `docs/DEPLOY.md`

- [ ] **Step 1:** `Procfile` 생성 (Render가 start 명령 자동 감지용 백업):
```
web: python run_server.py
```

- [ ] **Step 2:** `docs/DEPLOY.md` 생성:
```markdown
# Render 배포 / 복구 런북

프론트(`politics_front`)의 프로덕션 API URL = https://politics-backend-9vp2.onrender.com
이 백엔드는 Render의 GitHub 연동으로 `main` 푸시 시 자동 재배포된다.

## 1. 서비스 정지 해제
Render 대시보드 → `politics-backend` 서비스 → 정지(suspend) 상태면 Resume.
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
| FIREBASE_PRIVATE_KEY_ID | (새 키: 12f06af51e0c2d8a244de5467461c9ae9c493dab) |
| FIREBASE_PRIVATE_KEY | (새 키 private_key 값, `\n` 포함 그대로) |
| FIREBASE_CLIENT_EMAIL | firebase-adminsdk-1h5rn@koreanpolitical.iam.gserviceaccount.com |
| FIREBASE_CLIENT_ID | (JSON의 client_id) |
| FIREBASE_AUTH_URI | https://accounts.google.com/o/oauth2/auth |
| FIREBASE_TOKEN_URI | https://oauth2.googleapis.com/token |
| FIREBASE_AUTH_PROVIDER_X509_CERT_URL | https://www.googleapis.com/oauth2/v1/certs |
| FIREBASE_CLIENT_X509_CERT_URL | (JSON의 client_x509_cert_url) |
| ADMIN_KEY | (관리자 엔드포인트 보호용 임의 문자열) |
| GOOGLE_API_KEY | (Gemini 키 — 수집/AI 쓸 때) |
| AI_THROTTLE_SEC | 2 |

⚠️ FIREBASE_PRIVATE_KEY 는 한 줄로 `\n` 포함해 붙여넣기 (코드가 실제 줄바꿈으로 변환).

## 4. 배포 & 검증
- main 푸시 시 자동 배포(또는 Manual Deploy).
- 검증: `curl https://politics-backend-9vp2.onrender.com/health` → 200
- `curl https://politics-backend-9vp2.onrender.com/api/issues` → 시드된 이슈 2건
- 프론트(koreanpolitical.web.app) 새로고침 → 데이터 로드 확인

## 5. (선택) 정기 수집
Render Cron Job 또는 외부 스케줄러가 주기적으로
`POST /api/news/collect` 를 헤더 `X-Admin-Key: <ADMIN_KEY>` 와 호출.
(docs/scheduler.md 참고)
```

- [ ] **Step 3:** Commit
```bash
git add Procfile docs/DEPLOY.md
git commit -m "docs(deploy): Procfile + Render recovery runbook"
```

---

## Task 3: 로컬 전체 구동 스모크 테스트 (실 Firestore)

**목적:** 배포할 코드를 새 키로 **로컬에서 실제 기동**해 전 엔드포인트가 도는지 증명한다. 여기서 통과하면 Render에서도 같은 코드+env로 동작.

- [ ] **Step 1:** 전체 의존성 설치 — Run: `source .venv/bin/activate && pip install -q -r requirements.txt && echo ok`

- [ ] **Step 2:** 서버 백그라운드 기동 (.env 자동 로드) — Run:
```bash
cd /Users/manager/side/politics_backend && source .venv/bin/activate
(python run_server.py > /tmp/bk_render_test.log 2>&1 &) ; sleep 8 ; tail -5 /tmp/bk_render_test.log
```
Expected: uvicorn 기동 로그, "Firebase 초기화 완료".

- [ ] **Step 3:** 엔드포인트 스모크 — Run:
```bash
for p in "/health" "/api/news/list?limit=2" "/api/issues" "/api/members" "/api/politics/statements"; do
  echo -n "$p -> "; curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:8000$p"
done
curl -s "http://localhost:8000/api/issues" | python3 -c "import sys,json;d=json.load(sys.stdin);print('issues:',len(d['data']))"
```
Expected: 전부 200, issues: 2. (실패 코드가 있으면 원인 수정 후 재기동)

- [ ] **Step 4:** 인증 왕복 스모크(선택) — register→login→/me 200 확인. (실패 시 수정)

- [ ] **Step 5:** 서버 종료 — Run: `pkill -f run_server.py ; pkill -f "uvicorn main:app" ; echo stopped`

- [ ] **Step 6:** (스모크에서 코드 수정이 있었으면) Commit.

---

## Task 4: Render 복구 (인프라 — 사용자 실행)

`docs/DEPLOY.md` 런북대로 사용자가 Render 대시보드에서 실행:
- [ ] 서비스 정지 해제(Resume) / 정지 사유 해결
- [ ] 환경변수(FIREBASE_* 새 키, ADMIN_KEY, GOOGLE_API_KEY) 설정
- [ ] Start Command 확인 (`python run_server.py`)
- [ ] 배포(자동/수동) 후 `curl .../health` 200, `/api/issues` 2건, 프론트 로드 확인

---

## Task 5: (선택) 정기 수집 스케줄러
Render Cron Job이 `POST /api/news/collect` 를 `X-Admin-Key` 헤더로 주기 호출. (docs/scheduler.md)

---

## Self-Review 메모
- 스펙 커버리지: CORS(T1)·배포설정(T2)·코드 사전검증(T3)·인프라 복구(T4)·스케줄러(T5). 라이브 복구에 필요한 코드/인프라 모두 포함.
- 한계: T4는 Render 대시보드 접근이 필요해 사용자 실행. 코드 쪽(T1~T3)은 로컬 실 Firestore로 사전 검증 가능.
