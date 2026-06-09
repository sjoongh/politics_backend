# 의원 책임성 (프로필 + 전과) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 국회의원 프로필 + 전과(확정 판결) 조회/관리 API를 원본 백엔드 스타일로 구축하되, 법적 가드레일(확정 전과만 노출·출처 강제·면책 고지)을 강제한다.

**Architecture:** 원본 플랫 구조(`routers/`·`services/`·`models/model.py`). **법적 핵심 로직은 firebase 비의존 순수 모듈 `utils/member_rules.py`로 분리해 pytest로 실제 검증**, Firestore 접근(service)·라우터는 firebase 자격증명이 없어 `py_compile`+리뷰. 관리 엔드포인트는 `X-Admin-Key`(env `ADMIN_KEY`) 보호.

**Tech Stack:** Python, FastAPI, pydantic[email], google-cloud-firestore(원본), pytest(순수 로직 테스트용 로컬 venv).

**검증:** 순수 로직/모델 = pytest TDD(firebase 불필요). service/router = `py_compile` 문법 + 코드리뷰(실행은 배포/Firebase env에서). 작업 전 `git checkout -b feat/member-accountability`. 작업 디렉토리 `/Users/manager/side/politics_backend`.

---

## 기존 코드(참고)
- `models/model.py`: 모든 pydantic 모델 한 파일. `ResponseModel{success,message,data}`. `from pydantic import BaseModel, EmailStr`. (EmailStr 때문에 import 시 email-validator 필요)
- `services/X_service.py`: 클래스 + `from firebase.firebase_config import db` + `async def` + 싱글턴. **import 시 firebase 자격증명 필요** → 로컬 import 불가.
- `routers/X_router.py`: `router=APIRouter()`, main.py에서 `prefix`로 등록. 응답 `{success,message,data}`.
- `main.py`: `from routers import ..., member_router` 추가 + `app.include_router(member_router.router, prefix="/api/members")`.

## 파일 구조
| 파일 | 책임 | 검증 |
|------|------|------|
| `utils/member_rules.py` | 법적 순수 로직(확정필터·출처검사·면책문구) | pytest |
| `models/model.py` (수정) | CriminalRecord, MemberCreate 추가 | pytest |
| `services/member_service.py` | db CRUD + rules 적용 | py_compile |
| `routers/member_router.py` | 엔드포인트 + X-Admin-Key | py_compile |
| `main.py` (수정) | 라우터 등록 | py_compile |
| `data/sample_members.json` + `scripts/seed_members.py` | 가공 예시 시드 | (실행 안 함) |
| `tests/test_member_rules.py`, `tests/test_member_models.py` | 테스트 | pytest |

---

## Task 1: 로컬 테스트 셋업 + 모델

**Files:** Create `.venv`(gitignore), `tests/test_member_models.py`. Modify `models/model.py`, `.gitignore`.

- [ ] **Step 1: 테스트용 경량 venv (firebase 불필요)**
Run:
```bash
cd /Users/manager/side/politics_backend && python3.11 -m venv .venv && source .venv/bin/activate && pip install -q "pydantic[email]>=2.8.2" pytest>=8 && python -V
```
Expected: 설치 완료, Python 3.11.x.

- [ ] **Step 2: `.gitignore`에 `.venv/` 보장**
Run: `grep -qxF '.venv/' .gitignore || echo '.venv/' >> .gitignore` 그리고 `grep -n '.venv' .gitignore` 확인.

- [ ] **Step 3: 실패 테스트 `tests/test_member_models.py`**
```python
import pytest
from pydantic import ValidationError
from models.model import CriminalRecord, MemberCreate


def test_criminal_record_requires_source_url():
    rec = CriminalRecord(offense="공직선거법위반", disposition="벌금 100만원", year="2021", source_url="http://nec/1")
    assert rec.is_final is True
    assert rec.source_url == "http://nec/1"
    with pytest.raises(ValidationError):
        CriminalRecord(offense="x", disposition="y")  # source_url 누락


def test_member_create_defaults():
    m = MemberCreate(name="홍길동")
    assert m.party is None
    assert m.criminal_records == []


def test_member_create_with_records():
    m = MemberCreate(
        name="홍길동", party="무소속", district="서울 중구",
        criminal_records=[{"offense": "도로교통법위반", "disposition": "벌금 50만원", "year": "2019", "source_url": "http://nec/2"}],
    )
    assert isinstance(m.criminal_records[0], CriminalRecord)
    assert m.criminal_records[0].is_final is True
```

- [ ] **Step 4: 실패 확인** — Run: `source .venv/bin/activate && python -m pytest tests/test_member_models.py -v` → FAIL (ImportError: CriminalRecord).

- [ ] **Step 5: `models/model.py`에 추가** (파일 끝에, 기존 내용 유지)
```python
# 국회의원 책임성 (프로필 + 전과)
class CriminalRecord(BaseModel):
    offense: str            # 죄명
    disposition: str        # 형/처분 (예: "벌금 100만원")
    year: Optional[str] = None
    is_final: bool = True   # 확정 여부 (False면 노출 제외)
    source_url: str         # 공식 출처 (필수)

class MemberCreate(BaseModel):
    name: str
    party: Optional[str] = None
    district: Optional[str] = None
    committee: Optional[str] = None
    term: Optional[str] = None
    photo_url: Optional[str] = None
    source_url: Optional[str] = None
    criminal_records: List[CriminalRecord] = []
```
(`BaseModel`, `Optional`, `List`는 model.py 상단에서 이미 import됨.)

- [ ] **Step 6: 통과 확인** — Run: `source .venv/bin/activate && python -m pytest tests/test_member_models.py -v` → 3 passed.

- [ ] **Step 7: Commit**
```bash
git add models/model.py tests/test_member_models.py .gitignore
git commit -m "feat(members): CriminalRecord/MemberCreate models + tests"
```

---

## Task 2: 법적 순수 로직 (member_rules)

**Files:** Create `utils/member_rules.py`, `tests/test_member_rules.py`

- [ ] **Step 1: 실패 테스트 `tests/test_member_rules.py`**
```python
from utils.member_rules import confirmed_records, has_missing_source, criminal_count, MEMBER_DISCLAIMER


def _recs():
    return [
        {"offense": "a", "disposition": "벌금", "is_final": True, "source_url": "http://s/1"},
        {"offense": "b", "disposition": "수사중", "is_final": False, "source_url": "http://s/2"},
    ]


def test_confirmed_records_filters_non_final():
    out = confirmed_records(_recs())
    assert len(out) == 1
    assert out[0]["offense"] == "a"
    assert confirmed_records([]) == []
    assert confirmed_records(None) == []


def test_criminal_count_counts_only_final():
    assert criminal_count(_recs()) == 1
    assert criminal_count(None) == 0


def test_has_missing_source_detects_empty_or_absent():
    assert has_missing_source([{"offense": "a", "source_url": ""}]) is True
    assert has_missing_source([{"offense": "a"}]) is True
    assert has_missing_source([{"offense": "a", "source_url": "  "}]) is True
    assert has_missing_source([{"offense": "a", "source_url": "http://s/1"}]) is False
    assert has_missing_source([]) is False


def test_disclaimer_mentions_official_and_final():
    assert "선거관리위원회" in MEMBER_DISCLAIMER
    assert "확정" in MEMBER_DISCLAIMER
```

- [ ] **Step 2: 실패 확인** — Run: `source .venv/bin/activate && python -m pytest tests/test_member_rules.py -v` → FAIL.

- [ ] **Step 3: `utils/member_rules.py` 구현** (firebase import 절대 금지 — 순수 함수만)
```python
"""의원 책임성 법적 가드레일 순수 로직 (firebase 비의존, 테스트 대상)."""

MEMBER_DISCLAIMER = (
    "본 정보는 중앙선거관리위원회 공직선거 후보자 공개자료 등 공식 출처를 기반으로 하며, "
    "확정 판결만 표기합니다. 오류가 있을 경우 정정 요청을 받습니다."
)


def confirmed_records(records):
    """확정(is_final=True) 전과만 반환."""
    return [r for r in (records or []) if r.get("is_final", False)]


def criminal_count(records):
    """확정 전과 건수."""
    return len(confirmed_records(records))


def has_missing_source(records):
    """전과 중 source_url이 비었거나 없는 게 하나라도 있으면 True."""
    return any(not (r.get("source_url") or "").strip() for r in (records or []))
```

- [ ] **Step 4: 통과 확인** — Run: `source .venv/bin/activate && python -m pytest tests/test_member_rules.py -v` → 4 passed.

- [ ] **Step 5: Commit**
```bash
git add utils/member_rules.py tests/test_member_rules.py
git commit -m "feat(members): legal guardrail pure logic (confirmed-only, source-required) + tests"
```

---

## Task 3: MemberService (Firestore)

**Files:** Create `services/member_service.py`. (firebase 의존 → import 불가, `py_compile`만.)

- [ ] **Step 1: `services/member_service.py` 구현**
```python
import uuid
from datetime import datetime
from typing import Optional

from firebase.firebase_config import db
from models.model import MemberCreate
from utils.member_rules import confirmed_records, criminal_count, has_missing_source, MEMBER_DISCLAIMER

COLLECTION = "members"


class MemberService:
    @staticmethod
    async def upsert_member(member: MemberCreate) -> dict:
        records = [r.dict() for r in member.criminal_records]
        if has_missing_source(records):
            return {"success": False, "message": "모든 전과 항목에 출처(source_url)가 필요합니다."}
        member_id = uuid.uuid4().hex
        data = member.dict()
        data["criminal_records"] = records
        data["id"] = member_id
        data["updated_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        db.collection(COLLECTION).document(member_id).set(data)
        return {"success": True, "message": "의원 정보 저장 성공", "data": {"member": data}}

    @staticmethod
    async def list_members(party: Optional[str] = None, limit: int = 20, offset: int = 0) -> dict:
        ref = db.collection(COLLECTION)
        query = ref.where("party", "==", party) if party else ref
        query = query.limit(limit).offset(offset)
        members = []
        for doc in query.stream():
            m = doc.to_dict()
            members.append({
                "id": doc.id,
                "name": m.get("name"),
                "party": m.get("party"),
                "district": m.get("district"),
                "committee": m.get("committee"),
                "term": m.get("term"),
                "photo_url": m.get("photo_url"),
                "criminal_count": criminal_count(m.get("criminal_records")),
            })
        return {"success": True, "message": "의원 목록 조회 성공", "data": {"members": members, "count": len(members)}}

    @staticmethod
    async def get_member(member_id: str) -> dict:
        doc = db.collection(COLLECTION).document(member_id).get()
        if not doc.exists:
            return {"success": False, "message": "의원을 찾을 수 없습니다."}
        m = doc.to_dict()
        m["id"] = doc.id
        m["criminal_records"] = confirmed_records(m.get("criminal_records"))  # 확정만 노출
        m["disclaimer"] = MEMBER_DISCLAIMER
        return {"success": True, "message": "의원 상세 조회 성공", "data": {"member": m}}


member_service = MemberService()
```

- [ ] **Step 2: 문법 검증** — Run: `cd /Users/manager/side/politics_backend && python3 -m py_compile services/member_service.py && echo "✓ syntax ok"` (실행/import는 firebase 필요라 생략).

- [ ] **Step 3: Commit**
```bash
git add services/member_service.py
git commit -m "feat(members): MemberService (upsert/list/get, confirmed-only, source-required)"
```

---

## Task 4: 라우터 + X-Admin-Key + main 등록

**Files:** Create `routers/member_router.py`. Modify `main.py`. (`py_compile`만.)

- [ ] **Step 1: `routers/member_router.py` 구현**
```python
import os
from typing import Optional, List

from fastapi import APIRouter, Header, HTTPException
from models.model import MemberCreate, ResponseModel
from services.member_service import member_service
from utils.member_rules import has_missing_source

router = APIRouter()


def _require_admin(x_admin_key: Optional[str]):
    expected = os.getenv("ADMIN_KEY")
    if not expected or x_admin_key != expected:
        raise HTTPException(status_code=401, detail="관리자 권한이 필요합니다.")


@router.get("", response_model=ResponseModel)
async def list_members(party: Optional[str] = None, limit: int = 20, offset: int = 0):
    return await member_service.list_members(party=party, limit=limit, offset=offset)


@router.get("/{member_id}", response_model=ResponseModel)
async def get_member(member_id: str):
    result = await member_service.get_member(member_id)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("message", "의원을 찾을 수 없습니다."))
    return result


@router.post("", response_model=ResponseModel)
async def create_member(member: MemberCreate, x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key")):
    _require_admin(x_admin_key)
    records = [r.dict() for r in member.criminal_records]
    if has_missing_source(records):
        raise HTTPException(status_code=400, detail="모든 전과 항목에 출처(source_url)가 필요합니다.")
    return await member_service.upsert_member(member)
```

- [ ] **Step 2: `main.py` 수정** — import 라인에 `member_router` 추가:
원래: `from routers import auth_router, bookmark_router, comment_router, feedback_router, news_router, notification_router, politics_router, statistic_router, summary_router, health_check_router`
→ 끝에 `, member_router` 추가.
그리고 `app.include_router(politics_router.router, prefix="/api/politics")` 다음 줄에 추가:
```python
app.include_router(member_router.router, prefix="/api/members")
```

- [ ] **Step 3: 문법 검증** — Run: `cd /Users/manager/side/politics_backend && python3 -m py_compile routers/member_router.py main.py && echo "✓ syntax ok"`.

- [ ] **Step 4: Commit**
```bash
git add routers/member_router.py main.py
git commit -m "feat(members): /api/members router (X-Admin-Key, 400 on missing source) + register"
```

---

## Task 5: 샘플 시드(가공) + 스크립트 + README + 전체 검증

**Files:** Create `data/sample_members.json`, `scripts/seed_members.py`. Modify `README.md`(있으면) 또는 docs.

- [ ] **Step 1: `data/sample_members.json` 작성** (실명·실제 전과 ❌ — 가공 예시. 운영 데이터는 공식 출처 확인 후 관리자 입력)
```json
[
  {
    "name": "예시의원A",
    "party": "예시당",
    "district": "서울 예시구",
    "committee": "예시위원회",
    "term": "22대",
    "photo_url": null,
    "source_url": "https://open.assembly.go.kr",
    "criminal_records": [
      {"offense": "예시법위반(가공 데이터)", "disposition": "벌금 100만원", "year": "2021", "is_final": true, "source_url": "https://info.nec.go.kr"}
    ]
  },
  {
    "name": "예시의원B",
    "party": "예시당2",
    "district": "부산 예시구",
    "committee": "예시위원회2",
    "term": "22대",
    "photo_url": null,
    "source_url": "https://open.assembly.go.kr",
    "criminal_records": []
  }
]
```

- [ ] **Step 2: `scripts/seed_members.py` 작성**
```python
"""의원 샘플 데이터를 Firestore에 적재한다(가공 예시).
사용: FIREBASE_* env 설정 후 python scripts/seed_members.py
"""
import asyncio
import json
from pathlib import Path

from models.model import MemberCreate
from services.member_service import member_service


async def main() -> None:
    path = Path(__file__).resolve().parent.parent / "data" / "sample_members.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    count = 0
    for item in raw:
        result = await member_service.upsert_member(MemberCreate(**item))
        if result.get("success"):
            count += 1
        else:
            print("skip:", result.get("message"))
    print(f"seeded {count} members")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 3: 시드 JSON이 모델로 파싱되는지 (firebase 없이)**
Run: `cd /Users/manager/side/politics_backend && source .venv/bin/activate && python -c "import json,pathlib; from models.model import MemberCreate; d=json.loads(pathlib.Path('data/sample_members.json').read_text()); ms=[MemberCreate(**x) for x in d]; print(len(ms),'members parse ok; A전과:', len(ms[0].criminal_records))"`
Expected: `2 members parse ok; A전과: 1`

- [ ] **Step 4: 전체 신규 파일 문법 검증 + 테스트**
Run:
```bash
cd /Users/manager/side/politics_backend && source .venv/bin/activate
python -m py_compile services/member_service.py routers/member_router.py scripts/seed_members.py main.py && echo "✓ syntax ok"
python -m pytest tests/test_member_rules.py tests/test_member_models.py -q
```
Expected: `✓ syntax ok`, 그리고 7 passed.

- [ ] **Step 5: 문서 갱신** — `docs/`에 짧은 메모 또는 README가 있으면 `## API`에 추가:
"GET /api/members · GET /api/members/{id} · POST /api/members (X-Admin-Key). 전과는 확정 판결만 노출, 출처(source_url) 필수, 응답에 disclaimer 포함. 운영 시 ADMIN_KEY 환경변수 설정."
README가 없으면 `docs/members.md`로 위 내용 작성.

- [ ] **Step 6: Commit**
```bash
git add data/sample_members.json scripts/seed_members.py docs/ README.md 2>/dev/null; git add -A
git commit -m "feat(members): sample seed + script + docs"
```
(.venv는 gitignore됨 — 스테이징 확인.)

---

## Self-Review 메모 (플랜 작성자)
- 스펙 커버리지: 모델(T1)·법적 순수로직(T2)·서비스(T3)·라우터+admin+main(T4)·시드/문서(T5). 가드레일 4개 모두: 확정만(confirmed_records, get_member), 출처필수(has_missing_source→400), 중립(필드만), 면책(MEMBER_DISCLAIMER, get_member에 부착).
- 플레이스홀더 없음: 모든 코드 실제 코드.
- 타입 일관성: `confirmed_records/has_missing_source/criminal_count/MEMBER_DISCLAIMER`가 rules·service·router·tests에서 동일 사용. `MemberCreate`/`CriminalRecord` 일관. service 메서드(upsert_member/list_members/get_member) 라우터와 일치.
- 검증 한계 명시: service/router는 firebase 의존이라 py_compile만. 법적 핵심 로직은 pytest로 실제 커버.

## 다음 단계
프론트 의원 프로필/검색 UI → 표결 기록(열린국회 API) → 공약 이행. 별도 plan.
