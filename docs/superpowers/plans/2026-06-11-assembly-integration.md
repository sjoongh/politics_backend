# 열린국회 연동: 의원 로스터·발의법안·표결 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (inline). Steps use `- [ ]`.

**Goal:** 열린국회정보 OpenAPI로 실제 22대 국회의원 명단·발의법안·본회의 표결을 가져와 의원 책임성 데이터를 공식 데이터로 채운다.

**Architecture:** envelope 파서는 firebase 비의존 순수 모듈(pytest). HTTP 클라이언트 + 동기화 서비스가 열린국회 API 호출 → Firestore `members`에 저장(doc id = MONA_CD). 의원 상세 API/프론트가 발의법안·표결 표시. **빈 KEY로도 읽기 동작 확인됨** → 실데이터 라이브 검증 가능.

**Tech Stack:** FastAPI(원본 백엔드), requests, React. 검증: pytest(파서) + **실 열린국회 API + 실 Firestore** 라이브.

**확인된 API (AGE=22):**
- 의원: `nwvrqwxyaytdsfvhu` → HG_NM,POLY_NM,ORIG_NM,CMIT_NM,UNITS,REELE_GBN_NM,HOMEPAGE,**MONA_CD**
- 발의법안: `nzmimeepazxkubdpn?AGE=22` → BILL_NAME,BILL_NO,PROPOSE_DT,PROC_RESULT,DETAIL_LINK,**RST_MONA_CD**(대표발의)
- 표결안건목록: `ncocpgfiaoituanbr?AGE=22` → BILL_ID,BILL_NAME,PROC_RESULT_CD,PROC_DT
- 의원별표결: `nojepdqqaweusdfbi?AGE=22&BILL_ID=<id>` → **MONA_CD**,HG_NM,**RESULT_VOTE_MOD**(찬성/반대/기권),BILL_NAME,VOTE_DATE,BILL_URL

**Envelope:** `{ "<svc>": [ {"head":[{"list_total_count":N},{"RESULT":{"CODE":"INFO-000"}}]}, {"row":[{...}]} ] }`. 오류 시 `{"RESULT":{"CODE":"ERROR-xxx","MESSAGE":...}}` 또는 head의 RESULT.CODE != INFO-000.

**환경변수:** `ASSEMBLY_API_KEY`(기본 "" — 읽기 동작하나 운영은 open.assembly.go.kr 키 권장), `ASSEMBLY_AGE`(기본 "22").

**⚖️ 법적:** 표결·발의는 공식 국회 기록=사실. 출처 링크(BILL_URL/DETAIL_LINK) 표기, 중립 서술. 점수화·등급은 방법론 공개 전엔 ❌.

작업 전 백엔드 `git checkout -b feat/assembly`, 프론트 동일. `.venv` 존재.

---

## Task 1: envelope 파서(순수) + API 클라이언트

**Files:** Create `utils/assembly_parse.py`, `tests/test_assembly_parse.py`, `services/assembly_client.py`

- [ ] **Step 1: 실패 테스트 `tests/test_assembly_parse.py`**
```python
from utils.assembly_parse import extract_rows


def test_extract_rows_ok():
    payload = {"svc": [
        {"head": [{"list_total_count": 1}, {"RESULT": {"CODE": "INFO-000"}}]},
        {"row": [{"A": 1}, {"A": 2}]},
    ]}
    assert extract_rows(payload, "svc") == [{"A": 1}, {"A": 2}]


def test_extract_rows_error_envelope():
    assert extract_rows({"RESULT": {"CODE": "ERROR-300", "MESSAGE": "x"}}, "svc") == []


def test_extract_rows_empty_or_malformed():
    assert extract_rows({}, "svc") == []
    assert extract_rows(None, "svc") == []
    assert extract_rows({"svc": [{"head": []}]}, "svc") == []
```

- [ ] **Step 2: 실패 확인** — `source .venv/bin/activate && python -m pytest tests/test_assembly_parse.py -v` → FAIL.

- [ ] **Step 3: `utils/assembly_parse.py`**
```python
"""열린국회 OpenAPI 응답 envelope 파서 (외부 의존 없음, 테스트 대상)."""


def extract_rows(payload, service):
    """표준 envelope에서 row 리스트 추출. 오류/빈 응답이면 []."""
    if not isinstance(payload, dict):
        return []
    blocks = payload.get(service)
    if not isinstance(blocks, list):
        return []
    for block in blocks:
        if isinstance(block, dict) and "row" in block and isinstance(block["row"], list):
            return block["row"]
    return []
```

- [ ] **Step 4: 통과 확인** — `python -m pytest tests/test_assembly_parse.py -v` → 3 passed.

- [ ] **Step 5: `services/assembly_client.py`** (HTTP, firebase 비의존)
```python
import os
import requests
from utils.assembly_parse import extract_rows

BASE = "https://open.assembly.go.kr/portal/openapi/"


def _key():
    return os.getenv("ASSEMBLY_API_KEY", "")


def fetch_rows(service: str, params: dict = None, p_index: int = 1, p_size: int = 100) -> list:
    """서비스 호출 후 row 리스트 반환. 실패 시 []."""
    q = {"KEY": _key(), "Type": "json", "pIndex": p_index, "pSize": p_size}
    if params:
        q.update(params)
    try:
        r = requests.get(BASE + service, params=q, timeout=20)
        return extract_rows(r.json(), service)
    except Exception:
        return []


def fetch_all(service: str, params: dict = None, p_size: int = 100, max_pages: int = 20) -> list:
    """페이지네이션으로 전체 row 수집(상한 max_pages)."""
    out = []
    for i in range(1, max_pages + 1):
        rows = fetch_rows(service, params=params, p_index=i, p_size=p_size)
        if not rows:
            break
        out.extend(rows)
        if len(rows) < p_size:
            break
    return out
```

- [ ] **Step 6: 클라이언트 라이브 스모크** — Run:
```bash
source .venv/bin/activate && python3 -c "from services.assembly_client import fetch_rows; r=fetch_rows('nwvrqwxyaytdsfvhu', p_size=2); print('의원 row:', len(r), r[0]['HG_NM'] if r else '-')"
```
Expected: `의원 row: 2 <이름>`.

- [ ] **Step 7: Commit**
```bash
git add utils/assembly_parse.py tests/test_assembly_parse.py services/assembly_client.py
git commit -m "feat(assembly): OpenAPI envelope parser (tested) + HTTP client"
```

---

## Task 2: 의원 로스터 동기화 (실제 의원으로 교체)

**Files:** Create `services/assembly_service.py`

- [ ] **Step 1: `services/assembly_service.py`** (sync_members)
```python
import os
from datetime import datetime

from firebase.firebase_config import db
from services.assembly_client import fetch_all, fetch_rows

AGE = os.getenv("ASSEMBLY_AGE", "22")
MEMBERS = "members"


def _now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


class AssemblyService:
    @staticmethod
    async def sync_members() -> dict:
        rows = fetch_all("nwvrqwxyaytdsfvhu", p_size=300, max_pages=3)
        if not rows:
            return {"success": False, "message": "의원 명단을 가져오지 못했습니다."}
        count = 0
        for m in rows:
            mona = m.get("MONA_CD")
            if not mona:
                continue
            doc = {
                "id": mona,
                "assembly_id": mona,
                "name": m.get("HG_NM"),
                "party": m.get("POLY_NM"),
                "district": m.get("ORIG_NM"),
                "committee": m.get("CMIT_NM"),
                "term": m.get("UNITS"),
                "reelection": m.get("REELE_GBN_NM"),
                "source_url": m.get("HOMEPAGE") or "https://open.assembly.go.kr",
                "updated_at": _now(),
            }
            db.collection(MEMBERS).document(mona).set(doc, merge=True)
            count += 1
        return {"success": True, "message": "의원 동기화 완료", "data": {"count": count}}


assembly_service = AssemblyService()
```

- [ ] **Step 2: 문법 + 라이브 동기화 검증** — Run:
```bash
source .venv/bin/activate && python3 -m py_compile services/assembly_service.py && python3 - <<'PY' 2>&1 | grep -vE "UserWarning|return query|Firebase 초기화|FutureWarning|google|^$|updates|README|https://git"
import asyncio
from services.assembly_service import assembly_service
from services.member_service import member_service
async def m():
    r = await assembly_service.sync_members()
    print("sync:", r["success"], r.get("data"))
    lst = await member_service.list_members(limit=3)
    print("members 샘플:", [(x["name"], x["party"]) for x in lst["data"]["members"]])
asyncio.run(m())
PY
```
Expected: `sync: True {'count': 300}` (또는 근사), 실제 의원 이름·정당 출력.

- [ ] **Step 3: Commit**
```bash
git add services/assembly_service.py
git commit -m "feat(assembly): sync real 22nd-assembly member roster into Firestore"
```

---

## Task 3: 의원별 발의법안 동기화

**Files:** Modify `services/assembly_service.py`

- [ ] **Step 1: `sync_bills` 메서드 추가** (AssemblyService 안, sync_members 다음)
```python
    @staticmethod
    async def sync_bills(max_pages: int = 5) -> dict:
        rows = []
        for i in range(1, max_pages + 1):
            page = fetch_rows("nzmimeepazxkubdpn", params={"AGE": AGE}, p_index=i, p_size=100)
            if not page:
                break
            rows.extend(page)
        # 대표발의자(RST_MONA_CD)별로 묶기
        by_member = {}
        for b in rows:
            mona = b.get("RST_MONA_CD")
            if not mona:
                continue
            by_member.setdefault(mona, []).append({
                "name": b.get("BILL_NAME"),
                "no": b.get("BILL_NO"),
                "date": b.get("PROPOSE_DT"),
                "result": b.get("PROC_RESULT"),
                "link": b.get("DETAIL_LINK"),
            })
        count = 0
        for mona, bills in by_member.items():
            ref = db.collection(MEMBERS).document(mona)
            if not ref.get().exists:
                continue
            ref.update({"bills": bills[:30], "bill_count": len(bills), "updated_at": _now()})
            count += 1
        return {"success": True, "message": "발의법안 동기화 완료", "data": {"members_updated": count}}
```

- [ ] **Step 2: 라이브 검증** — Run:
```bash
source .venv/bin/activate && python3 - <<'PY' 2>&1 | grep -vE "UserWarning|return query|Firebase 초기화|FutureWarning|google|^$|updates|README|https://git"
import asyncio
from services.assembly_service import assembly_service
async def m():
    r = await assembly_service.sync_bills(max_pages=2)
    print("bills sync:", r["success"], r.get("data"))
asyncio.run(m())
PY
```
Expected: `bills sync: True {'members_updated': N}` (N>0).

- [ ] **Step 3: Commit**
```bash
git add services/assembly_service.py
git commit -m "feat(assembly): sync member-sponsored bills (RST_MONA_CD grouping)"
```

---

## Task 4: 주요 표결 동기화 (의원별 찬반)

**Files:** Modify `services/assembly_service.py`

- [ ] **Step 1: `sync_votes` 메서드 추가** (최근 N개 안건의 의원별 표결을 의원 doc에 누적)
```python
    @staticmethod
    async def sync_votes(num_bills: int = 10) -> dict:
        bills = fetch_rows("ncocpgfiaoituanbr", params={"AGE": AGE}, p_index=1, p_size=num_bills)
        if not bills:
            return {"success": False, "message": "표결 안건을 가져오지 못했습니다."}
        votes_by_member = {}
        for b in bills:
            bid = b.get("BILL_ID")
            if not bid:
                continue
            rows = fetch_all("nojepdqqaweusdfbi", params={"AGE": AGE, "BILL_ID": bid}, p_size=300, max_pages=2)
            for v in rows:
                mona = v.get("MONA_CD")
                if not mona:
                    continue
                votes_by_member.setdefault(mona, []).append({
                    "bill": v.get("BILL_NAME"),
                    "vote": v.get("RESULT_VOTE_MOD"),
                    "date": v.get("VOTE_DATE"),
                    "link": v.get("BILL_URL"),
                })
        count = 0
        for mona, votes in votes_by_member.items():
            ref = db.collection(MEMBERS).document(mona)
            if not ref.get().exists:
                continue
            ref.update({"votes": votes[:30], "updated_at": _now()})
            count += 1
        return {"success": True, "message": "표결 동기화 완료", "data": {"members_updated": count, "bills": len(bills)}}
```

- [ ] **Step 2: 라이브 검증** — Run:
```bash
source .venv/bin/activate && python3 - <<'PY' 2>&1 | grep -vE "UserWarning|return query|Firebase 초기화|FutureWarning|google|^$|updates|README|https://git"
import asyncio
from firebase.firebase_config import db
from services.assembly_service import assembly_service
async def m():
    r = await assembly_service.sync_votes(num_bills=3)
    print("votes sync:", r["success"], r.get("data"))
    # 표결 들어간 의원 하나 확인
    for doc in db.collection("members").limit(20).stream():
        d = doc.to_dict()
        if d.get("votes"):
            print("샘플:", d["name"], d["votes"][0]); break
asyncio.run(m())
PY
```
Expected: `votes sync: True {...}`, 샘플 의원의 표결(찬성/반대).

- [ ] **Step 3: Commit**
```bash
git add services/assembly_service.py
git commit -m "feat(assembly): sync per-member roll-call votes (recent bills)"
```

---

## Task 5: API — 동기화 엔드포인트 (admin)

**Files:** Create `routers/assembly_router.py`, Modify `main.py`

- [ ] **Step 1: `routers/assembly_router.py`** (X-Admin-Key 보호)
```python
import os
from typing import Optional
from fastapi import APIRouter, Header, HTTPException
from models.model import ResponseModel
from services.assembly_service import assembly_service

router = APIRouter()


def _require_admin(x_admin_key: Optional[str]):
    expected = os.getenv("ADMIN_KEY")
    if not expected or x_admin_key != expected:
        raise HTTPException(status_code=401, detail="관리자 권한이 필요합니다.")


@router.post("/sync/members", response_model=ResponseModel)
async def sync_members(x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key")):
    _require_admin(x_admin_key)
    return await assembly_service.sync_members()


@router.post("/sync/bills", response_model=ResponseModel)
async def sync_bills(x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key")):
    _require_admin(x_admin_key)
    return await assembly_service.sync_bills()


@router.post("/sync/votes", response_model=ResponseModel)
async def sync_votes(x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key")):
    _require_admin(x_admin_key)
    return await assembly_service.sync_votes()
```

- [ ] **Step 2: `main.py` 등록** — import에 `assembly_router` 추가 + `app.include_router(member_router.router, prefix="/api/members")` 다음 줄에:
```python
app.include_router(assembly_router.router, prefix="/api/assembly")
```

- [ ] **Step 3: 검증** — `python3 -m py_compile routers/assembly_router.py main.py && echo ok`. `grep -n assembly_router main.py`.

- [ ] **Step 4: Commit**
```bash
git add routers/assembly_router.py main.py
git commit -m "feat(assembly): admin sync endpoints /api/assembly/sync/*"
```
> 참고: 의원 상세(`GET /api/members/{id}`)는 member doc 전체를 반환하므로 `bills`/`votes`가 자동 포함됨(member_service.get_member). 별도 수정 불필요.

---

## Task 6: 프론트 — 의원 상세에 발의법안·표결

**Files:** Modify `politics_front/src/components/MemberDetail.jsx`, `src/theme/tokens.css`

- [ ] **Step 1: `MemberDetail.jsx`** — disclaimer 직전(전과 섹션 다음)에 추가:
```jsx
            {Array.isArray(detail.votes) && detail.votes.length > 0 && (
              <>
                <div className="issue-section-title">🗳️ 주요 표결</div>
                <div className="issue-timeline">
                  {detail.votes.slice(0, 10).map((v, i) => (
                    <div key={i} className="issue-event">
                      <div className="issue-event__headline">
                        <span className={`vote-tag vote-tag--${v.vote === '찬성' ? 'yes' : v.vote === '반대' ? 'no' : 'etc'}`}>{v.vote}</span> {v.bill}
                      </div>
                      {v.link && <a className="issue-event__summary" href={v.link} target="_blank" rel="noreferrer">의안 보기</a>}
                    </div>
                  ))}
                </div>
              </>
            )}

            {Array.isArray(detail.bills) && detail.bills.length > 0 && (
              <>
                <div className="issue-section-title">📜 발의 법안 {detail.bill_count ? `(${detail.bill_count})` : ''}</div>
                <div className="issue-timeline">
                  {detail.bills.slice(0, 10).map((b, i) => (
                    <a key={i} className="persp-item" href={b.link} target="_blank" rel="noreferrer">
                      <span className="persp-item__src">{b.result || '처리중'}</span> {b.name}
                    </a>
                  ))}
                </div>
              </>
            )}
```

- [ ] **Step 2: `tokens.css` 끝에 추가**
```css

/* ===== 표결 태그 ===== */
.vote-tag { display: inline-block; font-size: 11px; font-weight: 700; color: #fff; padding: 1px 7px; border-radius: var(--radius-pill); margin-right: 6px; }
.vote-tag--yes { background: #16a34a; }
.vote-tag--no { background: #dc2626; }
.vote-tag--etc { background: #6b7280; }
```

- [ ] **Step 3: 빌드** — `cd /Users/manager/side/politics_front && CI=false npm run build 2>&1 | grep -E "Compiled|Failed"` → Compiled successfully.

- [ ] **Step 4: Commit**
```bash
git add src/components/MemberDetail.jsx src/theme/tokens.css
git commit -m "feat(members): show roll-call votes + sponsored bills in member detail"
```

---

## Self-Review
- 스펙 커버리지: 파서(T1)·로스터(T2)·발의법안(T3)·표결(T4)·API(T5)·프론트(T6). 확인된 실제 스키마 사용(추측 없음).
- 파서는 pytest, 동기화는 **실 열린국회 API + 실 Firestore** 라이브 검증.
- 타입 일관성: extract_rows→fetch_rows/fetch_all→sync_* (members/bills/votes 필드: name/party/.../bills[{name,no,date,result,link}]/votes[{bill,vote,date,link}]) → member_service.get_member 자동 반환 → 프론트 동일 키.
- 법적: 공식기록·출처링크·중립, 점수화 없음.

## 다음 (#5)
푸시 다이제스트 + 개인화. 별도 brainstorming→plan.
