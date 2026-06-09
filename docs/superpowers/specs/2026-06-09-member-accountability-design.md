# 의원 책임성 — 프로필 + 전과 (Design Spec)

작성일: 2026-06-09
대상: politics_backend (원본, 배포 source of truth). 플랫 구조(`routers/`·`services/`·`models/model.py`) 컨벤션.

## 1. 목표 & 범위
국회의원 책임성 데이터를 제공한다. **MVP = 의원 프로필 + 전과(확정 판결)**, 관리자 큐레이션 시드(공식 출처 인용).
**제외(후속):** 표결 기록, 공약 이행, 발의 법안, 프론트 UI(다음 슬라이스), 공식 API 라이브 연동.

## 2. 핵심 결정
- 데이터 수급 = **관리자 큐레이션 시드** (열린국회·선관위 공식자료를 수기/반자동으로, 출처 링크 명시). 라이브 API는 후속.
- 빌드 = **원본 백엔드 플랫 스타일**(services 클래스 + `db.collection` 직접 + `{success,message,data}`). 관리 엔드포인트는 **X-Admin-Key** 보호(원본 무방비 보완).

## 3. ⚖️ 법적 가드레일 (설계에 강제 — 변호사 자문은 출시 전 별도 권장)
1. **확정 판결만 노출**: API는 `is_final=true` 전과만 반환. 수사중/기소 ❌ (무죄추정·명예훼손 위험).
2. **출처 필수**: 모든 전과/프로필에 공식 `source_url`. 시드 시 전과에 source_url 없으면 **거부(400)**.
3. **사실·중립**: 죄명·형/처분·연도만. 평가·낙인·수식어 ❌.
4. **면책 고지**: 응답/화면에 "선관위 공직선거 후보자 공개자료 기반, 확정 판결만 표기" 취지 문구.
근거: 선관위가 공직선거법 §49로 후보자 전과를 공식 공개. 공인+공공의 이익+진실+확정판결 → 형법 §310 위법성 조각. 위 1~3으로 위험(수사중 단정·부정확·비방) 차단.

## 4. 데이터 모델 (`models/model.py`에 섹션 추가, pydantic)
```
CriminalRecord:
  offense: str            # 죄명
  disposition: str        # 형/처분 (예: "벌금 100만원", "징역 6월 집행유예")
  year: Optional[str]     # 판결 연도
  is_final: bool = True   # 확정 여부 (false면 노출 제외)
  source_url: str         # 공식 출처 (필수)

MemberCreate:
  name: str
  party: Optional[str] = None
  district: Optional[str] = None      # 지역구
  committee: Optional[str] = None
  term: Optional[str] = None          # 대수 (예: "22대")
  photo_url: Optional[str] = None
  source_url: Optional[str] = None    # 공식 프로필 출처
  criminal_records: List[CriminalRecord] = []
```
저장 시 서버가 `id`(이름+지역구 해시 또는 uuid), `updated_at` 부여. Firestore 컬렉션 `members`.

## 5. API (`routers/member_router.py`, main.py에서 prefix `/api/members`)
응답 `{success, message, data}`.
| Method | Path | 동작 | data |
|---|---|---|---|
| GET | `/api/members` (query: party, limit=20, offset=0) | 목록 | `{members:[{id,name,party,district,committee,term,photo_url, criminal_count}], count}` |
| GET | `/api/members/{id}` | 상세 | `{member:{...프로필..., criminal_records:[확정만], disclaimer}}` |
| POST | `/api/members` (X-Admin-Key) | 시드/업서트 | `{member}` |

규칙: 상세/목록은 **is_final=true 전과만** 노출·집계. POST 시 각 전과에 source_url 없으면 400. 상세에 `disclaimer` 문구 포함.

## 6. 서비스 (`services/member_service.py`)
- `MemberService` 클래스, `db.collection("members")` 직접.
- `upsert(member)`: id 생성/병합, 전과 source_url 검증, updated_at.
- `list_members(party, limit, offset)`: 목록 + 각 member의 확정 전과 count.
- `get_member(id)`: 상세, criminal_records를 is_final=true만 필터, disclaimer 부착.

## 7. 검증
- Firebase 자격증명 없어 로컬 실행 불가 → `py_compile` 문법 + 코드 리뷰. 실제 동작은 배포(또는 .env 제공) 시 확인.
- 시드 샘플은 **실명/실제 전과 데이터 대신 가공 예시**로 시작(법적 안전), 운영 데이터는 공식 출처 확인 후 관리자가 입력.

## 8. 성공 기준
- 의원 목록/상세 조회 + 관리자 시드 동작(원본 스타일).
- 확정 전과만 노출, source_url 강제, disclaimer 포함.
- 다음 슬라이스(프론트 의원 프로필 UI)가 소비할 계약 충족.

## 9. 후속 슬라이스
프론트 의원 프로필/검색 UI → 표결 기록(열린국회 API) → 공약 이행 → 발의 법안. 각 별도 spec.
