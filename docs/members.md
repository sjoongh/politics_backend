# 의원 책임성 (프로필 + 전과)

## API
- GET /api/members?party=&limit=&offset= — 의원 목록 (프로필 + 확정 전과 건수)
- GET /api/members/{id} — 의원 상세 (프로필 + 확정 전과만 + disclaimer)
- POST /api/members — 시드/업서트 (헤더 X-Admin-Key 필요)

## 법적 가드레일
- 확정 판결(is_final=true) 전과만 노출
- 모든 전과에 출처(source_url) 필수 — 없으면 400
- 응답에 면책 고지(disclaimer) 포함
- 운영: ADMIN_KEY 환경변수 설정 필요. 데이터는 선관위/열린국회 등 공식 출처 확인 후 입력.

## 시드
python scripts/seed_members.py (FIREBASE_* env 설정 필요). data/sample_members.json 은 가공 예시.
