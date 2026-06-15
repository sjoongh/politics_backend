# Vercel 배포 가이드

## 1. Vercel에 레포 연결
Vercel → New Project → `sjoongh/politics_backend` import. 프레임워크 프리셋: Other.
`vercel.json` / `api/index.py` / `requirements.txt`(슬림) 자동 인식.

## 2. 환경변수 (Vercel Project Settings → Environment Variables)
FIREBASE_TYPE, FIREBASE_PROJECT_ID, FIREBASE_PRIVATE_KEY_ID, FIREBASE_PRIVATE_KEY,
FIREBASE_CLIENT_EMAIL, FIREBASE_CLIENT_ID, FIREBASE_AUTH_URI, FIREBASE_TOKEN_URI,
FIREBASE_AUTH_PROVIDER_X509_CERT_URL, FIREBASE_CLIENT_X509_CERT_URL,
ADMIN_KEY, ASSEMBLY_API_KEY, SECRET_KEY  (값은 politics_backend/.env 참고)
GOOGLE_API_KEY  ← **AI 자연어 검색(/api/news/search/ai)이 런타임에 Gemini를 직접 호출하므로 필수.**
  없으면 검색은 항상 `fallback_keyword`(부분문자열) 모드로만 동작한다. (선택: GEMINI_MODEL, 기본 gemini-2.5-flash)

## 3. 배포 & 검증
Deploy → `https://<project>.vercel.app/health` → 200
`https://<project>.vercel.app/api/issues` → 이슈 목록

## 4. 수집(GitHub Actions)
레포 Settings → Secrets and variables → Actions 에 FIREBASE_* + GOOGLE_API_KEY 등록.
`.github/workflows/collect.yml`가 매시 실행(수동 실행도 가능).

## 5. 프론트 연결
배포 URL을 `politics_front/src/hooks/api.js` 프로덕션 baseURL로 교체 → web 재배포.
