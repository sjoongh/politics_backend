# 이슈 중심 개편 — 백엔드 구현 플랜

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 이슈 상세를 2초 안에 내고, 이슈 문서에 `digest`를 사전 계산하고, 뉴스 이슈 중복을 막고, 1차 소스를 뉴스 이슈에도 연결하고, 날짜별 판(edition)과 소스 목록 API를 제공한다.

**Architecture:** 순수 로직은 `utils/*.py`에 firebase 비의존 함수로 두고 pytest로 고정한다. 서비스(`services/*.py`)는 Firestore I/O만 담당한다. 기존 필드는 유지하고 새 필드만 추가한 뒤(1차 배포) backfill → 정제 → 조회 전환(2차 배포) 순으로 간다. 파이프라인은 `scripts/run_pipeline.py` 단일 진입점으로 모으고 실행당 Firestore 읽기 수와 Gemini 호출 수를 로그로 남긴다.

**Tech Stack:** Python 3.11, FastAPI, firebase-admin(동기 Firestore), httpx(Gemini REST), pytest. Vercel 서버리스(`api/index.py`), GitHub Actions 크론.

**Spec:** `/Users/manager/side/politics_front/docs/superpowers/specs/2026-11-10-issue-first-redesign-design.md` §3, §6, §8

## Global Constraints

- 기존 응답 필드 유지: `source_panels.{government, assembly_bill, assembly_vote, party}`, `perspectives`, `articles`, `events`, `official_links`. 제거는 `source_panels.media`만.
- 새 필드는 추가만: `article_meta`, `digest`, `active`, `merged_into`, `evidence_hash`, `stance_state`, `links`, `issue_ids`, `editions/*`.
- **무료 티어 하드 제약**: Firestore 읽기 5만/일, Gemini 20건/일. 무거운 파이프라인 단계는 3시간마다만 실행하고, 실행당 읽기 2,000건 이하. 유료 전환 없음.
- 성공 응답 `Cache-Control: public, s-maxage=300, stale-while-revalidate=3600`, 오류 응답 `no-store`.
- Firestore를 호출하는 라우트 핸들러는 `def`(스레드풀) 또는 `run_in_threadpool`. 새 핸들러는 전부 `def`.
- 파이프라인 무거운 실행 1회 읽기 2,000건 이하, 로그 `[meter] reads=N writes=N gemini=N`. 기사 400건·활성 이슈·최근 14일 소스는 `PipelineContext`로 실행당 1회만 읽는다.
- Gemini 호출은 전부 `utils/ai_budget.py`의 `try_acquire`를 통과한다. `GEMINI_DAILY_BUDGET` 기본 18. 종류별 상한: `summary` 10, `enrich` 8, `stance` 0(`STANCE_PRESS=1`일 때 4), `search`/`briefing`은 캐시 미스 시 남은 예산에서만.
- 템플릿 요약 문장("여러 매체가 보도한 현안입니다…", "…1차 소스를 묶은 이슈입니다") 금지. AI 요약이 없으면 `utils/fallback_summary.py`의 규칙 기반 요약.
- 법안 소스(`actor_name="국회"`, `position="propose"`)와 정당 언급 그룹은 입장(stance)에 넣지 않는다.
- 자동 연결(`auto`)은 `law_name` 전체 문자열(4자 이상) 또는 `bill.bill_name` 정확 포함일 때만. 약한 신호는 `pending`.
- 기존 기사 연결은 지우지 않는다. 크로스링크 신규 추가만 실행당 이슈별 12건.
- 일회성 스크립트는 `--dry-run`이 기본, 적용 전 대상 문서를 `backups/<script>-<timestamp>.jsonl`에 덤프.
- 테스트 실행: `cd /Users/manager/side/politics_backend && .venv/bin/python -m pytest -q`. 모든 신규 순수 함수는 `tests/test_<module>.py`.
- 커밋은 작업 단위로, 브랜치 `feat/issue-first-data`(worktree). PR마다 codex 리뷰 1회.

## Review Focus

1. `article_ids`에 있지만 `articles` 컬렉션에서 지워진 기사 → `get_all` 결과에 없음. 상세·digest가 누락 기사를 건너뛰고 카운트는 실제 존재 기사 기준이어야 한다. (Task 2, Task 5 테스트)
2. `published_at`이 빈 문자열이거나 형식이 섞인 소스(ISO UTC vs `YYYY-MM-DD`) → KST 날짜 변환이 예외 없이 `None`을 돌려주고 판·커서에서 제외되어야 한다. (Task 11 테스트)
3. `merged_into`가 서로를 가리키는 두 문서 → `resolve_issue_id`가 무한 루프 없이 3단에서 멈추고 마지막 id를 돌려줘야 한다. (Task 1 테스트)
4. `party_breakdown`에 "무소속"만 있거나 비어 있는 표결 → stance에 빈 정당 행이 생기지 않아야 한다. (Task 5 테스트)
5. 커서가 조작되거나 깨진 base64 → 400이 아니라 첫 페이지로 처리하고 `next_cursor`는 정상 생성. (Task 7 테스트)

---

### Task 1: 병합 id 해석과 `active` 플래그

**Files:**
- Create: `utils/issue_merge_rules.py`, `tests/test_issue_merge_rules.py`
- Modify: `services/issue_service.py:57-58`(get_detail 진입), `routers/share_router.py:65`(`_fetch_issue_meta`)

**Interfaces:**
- Produces: `follow_merge(issue_id: str, lookup: Callable[[str], dict|None], max_hops: int = 3) -> str` — `lookup`이 돌려준 문서에 `merged_into`가 있으면 따라간다. 순환·초과 시 마지막 유효 id.
- Produces: `IssueService.resolve_issue_id(issue_id: str) -> str` (동기, Firestore `get` 최대 3회).

- [ ] **Step 1: 실패 테스트**

```python
# tests/test_issue_merge_rules.py
from utils.issue_merge_rules import follow_merge

def test_follow_single_hop():
    docs = {"a": {"merged_into": "b"}, "b": {}}
    assert follow_merge("a", docs.get) == "b"

def test_follow_stops_on_cycle():
    docs = {"a": {"merged_into": "b"}, "b": {"merged_into": "a"}}
    assert follow_merge("a", docs.get) in ("a", "b")  # 종료가 핵심

def test_follow_missing_returns_input():
    assert follow_merge("zzz", lambda _id: None) == "zzz"

def test_follow_max_hops():
    docs = {"a": {"merged_into": "b"}, "b": {"merged_into": "c"}, "c": {"merged_into": "d"}, "d": {"merged_into": "e"}, "e": {}}
    assert follow_merge("a", docs.get, max_hops=3) == "d"
```

- [ ] **Step 2: 실패 확인** — Run: `.venv/bin/python -m pytest tests/test_issue_merge_rules.py -q` → ImportError
- [ ] **Step 3: `utils/issue_merge_rules.py`에 `follow_merge` 구현** (방문 집합으로 순환 차단)
- [ ] **Step 4: 통과 확인**
- [ ] **Step 5: `IssueService.resolve_issue_id` 추가**(`@staticmethod def`, `follow_merge(issue_id, lambda i: (db.collection("issues").document(i).get().to_dict()))`). `get_detail` 첫 줄에서 `issue_id = self.resolve_issue_id(issue_id)`. 응답 `data.id`는 해석된 id. `share_router._fetch_issue_meta`도 같은 헬퍼로 해석 후 읽기.
- [ ] **Step 6: 커밋** `feat(issues): resolve merged issue ids in detail and share`

### Task 2: 이슈 상세 일괄 조회·페이지·캐시

**Files:**
- Create: `utils/cursor.py`, `tests/test_cursor.py`, `utils/http_cache.py`, `utils/doc_order.py`, `tests/test_doc_order.py`
- Modify: `services/issue_service.py:57-98`, `routers/issue_router.py:22-27`, `vercel.json`

**Interfaces:**
- Produces: `encode_cursor(d: dict) -> str`, `decode_cursor(s: str|None) -> dict` (깨진 입력은 `{}`). base64url(JSON).
- Produces: `order_by_ids(docs: list[dict], ids: list[str], key="id") -> list[dict]` — ids 순서대로, 없는 id는 건너뜀.
- Produces: `cache_headers(ok: bool) -> dict[str, str]`.
- Produces: `IssueService.get_detail(issue_id, article_limit=30) -> dict` — `data.articles`는 최신 30건, `data.article_total`, `data.articles_cursor`(다음 페이지 커서 또는 None). `source_panels.media` 없음.
- Produces: `IssueService.list_articles(issue_id, cursor: str|None, limit=30) -> dict` — `data.items`, `data.next_cursor`. 라우트 `GET /api/issues/{issue_id}/articles`.

- [ ] **Step 1: 실패 테스트**

```python
# tests/test_cursor.py
from utils.cursor import encode_cursor, decode_cursor
def test_roundtrip(): assert decode_cursor(encode_cursor({"o": 30})) == {"o": 30}
def test_garbage_is_empty(): assert decode_cursor("!!notbase64") == {}
def test_none_is_empty(): assert decode_cursor(None) == {}

# tests/test_doc_order.py
from utils.doc_order import order_by_ids
def test_orders_and_skips_missing():
    docs = [{"id": "b"}, {"id": "a"}]
    assert [d["id"] for d in order_by_ids(docs, ["a", "x", "b"])] == ["a", "b"]
```

- [ ] **Step 2: 실패 확인**
- [ ] **Step 3: 세 유틸 구현**
- [ ] **Step 4: 통과 확인**
- [ ] **Step 5: `get_detail` 재작성** — `article_ids` 전체 중 앞 30개(이미 날짜 역순으로 유지됨, Task 4 이후)만 `db.get_all([refs])`로 읽고 `order_by_ids`. `perspectives`·`party`는 **Task 4의 `article_meta`가 있으면 그걸로**, 없으면 읽은 30건으로 계산(호환). `source_items`는 `issue_ids array_contains`(Task 9 이후) 또는 현재 `issue_id ==` 둘 다 조회해 합집합(id 중복 제거). `media` 키 제거. `async def` → `def`.
- [ ] **Step 6: `list_articles` 구현**(오프셋 커서 `{"o": n}`), 라우터에 `GET /{issue_id}/articles` 추가. 라우터의 두 핸들러를 `def`로 바꾸고 `Response` 헤더에 `cache_headers(result["success"])` 적용.
- [ ] **Step 7: `vercel.json`에 `"regions": ["icn1"]` 추가**
- [ ] **Step 8: 로컬 측정** — Run: `.venv/bin/uvicorn main:app --port 8000 &` 후 `for i in 1 2 3; do curl -s -o /dev/null -w "%{time_total}\n" localhost:8000/api/issues/609c190844a5417c87695945e7bef25e; done` → 세 번 모두 3초 이내(로컬은 서울 Firestore까지 왕복 포함)
- [ ] **Step 9: 커밋** `perf(issues): batch article reads, paginate, cache headers, icn1 region`

### Task 3: AI 예산과 근거 해시

**Files:**
- Create: `utils/ai_budget.py`, `tests/test_ai_budget.py`, `utils/evidence_hash.py`, `tests/test_evidence_hash.py`
- Modify: `utils/gemini_rest.py:46`(`_generate` 진입에서 예산 확인)

**Interfaces:**
- Produces: `class AiBudget(limit: int, today: str, store, per_kind: dict[str,int] | None = None)` with `try_acquire(kind: str, n: int = 1) -> bool`(전체 한도와 종류별 한도 둘 다 확인), `used() -> int`, `mark_exhausted()`. `store`는 `get() -> dict`, `set(dict)` 두 메서드(테스트는 dict 기반 가짜, 운영은 `_meta/ai_budget_{YYYY-MM-DD}` 문서). 기본 `per_kind = {"summary": 10, "enrich": 8, "stance": 0}`.
- Produces: 모듈 함수 `budget() -> AiBudget`(싱글턴, `GEMINI_DAILY_BUDGET` env, KST 날짜), `_generate(prompt, *, json_mode, timeout, kind="misc")`가 `budget().try_acquire(kind)` 실패 시 `(None, "budget")` 반환.
- Produces: `evidence_hash(article_ids: list[str], source_ids: list[str] = ()) -> str` — 정렬 후 sha1 12자.

- [ ] **Step 1: 실패 테스트**

```python
# tests/test_ai_budget.py
from utils.ai_budget import AiBudget
class Mem:
    def __init__(s): s.d = {}
    def get(s): return dict(s.d)
    def set(s, v): s.d = dict(v)
def test_acquire_until_limit():
    b = AiBudget(limit=2, today="2026-11-10", store=Mem())
    assert b.try_acquire("summary") and b.try_acquire("summary")
    assert not b.try_acquire("summary")
    assert b.used() == 2
def test_counts_per_kind():
    b = AiBudget(limit=5, today="2026-11-10", store=Mem(), per_kind={"stance": 2}); b.try_acquire("stance", 2)
    assert b.store.get()["by_kind"]["stance"] == 2
    assert not b.try_acquire("stance")        # 종류별 한도
def test_default_stance_is_zero():
    assert not AiBudget(limit=18, today="d", store=Mem()).try_acquire("stance")
def test_exhausted_blocks_all():
    b = AiBudget(limit=18, today="d", store=Mem()); b.mark_exhausted(); assert not b.try_acquire("summary")

# tests/test_evidence_hash.py
from utils.evidence_hash import evidence_hash
def test_order_independent(): assert evidence_hash(["a","b"]) == evidence_hash(["b","a"])
def test_sources_change_hash(): assert evidence_hash(["a"]) != evidence_hash(["a"], ["s1"])
```

- [ ] **Step 2: 실패 확인** → **Step 3: 구현** → **Step 4: 통과 확인**
- [ ] **Step 5: `_generate`에 `kind` 인자와 예산 확인 추가**. 기존 호출부(`parse_query`→`kind="search"`, `synthesize_briefing`→`"briefing"`, `enrich_source`→`"enrich"`, `summarize_issue`→`"summary"`) 갱신. 429 응답(`http_429`)을 받으면 `budget().mark_exhausted()`로 그날 남은 호출을 즉시 거부.
- [ ] **Step 6: 기존 테스트 통과 확인** — Run: `.venv/bin/python -m pytest -q`
- [ ] **Step 7: 커밋** `feat(ai): shared daily Gemini budget and evidence hash`

### Task 4: `article_meta` 유지와 backfill

**Files:**
- Create: `utils/article_meta.py`, `tests/test_article_meta.py`, `scripts/backfill_issues.py`
- Modify: `services/issue_service.py`(`add_articles`), `services/news_issue_service.py:113-123`, `services/source_link_service.py:92-96`(crosslink 기사 추가)

**Interfaces:**
- Produces: `meta_for(article: dict) -> dict` → `{"source": str, "leaning": str, "at": str}` (`leaning`은 `source_bias.source_leaning`, `at`은 `created_at` ISO 또는 `published_at`).
- Produces: `merge_meta(existing: dict, articles: list[dict]) -> dict` (id → meta, 기존 유지).
- Produces: `sorted_article_ids(meta: dict) -> list[str]` — `at` 내림차순.
- Produces: `scripts/backfill_issues.py article-meta [--apply]` — 이슈별 `article_ids`를 `get_all`로 읽어 `article_meta` 채우고 `article_ids`를 날짜 역순으로 재정렬. dry-run은 이슈 수·기사 수·누락 기사 수 출력.

- [ ] **Step 1: 실패 테스트**

```python
# tests/test_article_meta.py
from utils.article_meta import meta_for, merge_meta, sorted_article_ids
def test_meta_for_uses_leaning():
    m = meta_for({"id": "a", "source": "한겨레", "created_at": "2026-11-10T01:00:00+00:00"})
    assert m == {"source": "한겨레", "leaning": "left", "at": "2026-11-10T01:00:00+00:00"}
def test_merge_keeps_existing():
    out = merge_meta({"a": {"source": "x", "leaning": "unknown", "at": "2026-01-01"}}, [{"id": "b", "source": "연합뉴스", "created_at": "2026-02-01"}])
    assert set(out) == {"a", "b"}
def test_sorted_desc():
    meta = {"a": {"at": "2026-01-01"}, "b": {"at": "2026-03-01"}}
    assert sorted_article_ids(meta) == ["b", "a"]
```

- [ ] **Step 2: 실패 확인** → **Step 3: 구현** → **Step 4: 통과 확인**
- [ ] **Step 5: 기사 연결 쓰기 경로 3곳에서 `article_meta` 갱신과 `article_ids = sorted_article_ids(meta)` 적용** (crosslink는 이미 로드한 `arts`에서 메타 생성 → 추가 읽기 없음).
- [ ] **Step 6: `scripts/backfill_issues.py` 뼈대**(argparse 서브커맨드, `--apply`, 백업 덤프 함수 `dump_backup(name, docs)`), `article-meta` 서브커맨드 구현.
- [ ] **Step 7: dry-run 실행** — Run: `.venv/bin/python scripts/backfill_issues.py article-meta` → `issues=65 articles=NNN missing=M` 형식 출력
- [ ] **Step 8: 커밋** `feat(issues): maintain article_meta on link paths; backfill script`

### Task 5: digest 순수 계산

**Files:**
- Create: `utils/issue_digest.py`, `utils/ministries.py`, `tests/test_issue_digest.py`

**Interfaces:**
- Produces: `count_sources(sources: list[dict]) -> dict` → `{"gov","bill","vote"}` (`type` 기준).
- Produces: `representative_vote(sources) -> dict|None` → `{"source_id","bill_name","date","yes","no","abstain","result"}`, `published_at` 최신 표결.
- Produces: `ministry_of(text: str) -> str` — `MINISTRIES` 목록 중 첫 등장, 없으면 `"정부"`.
- Produces: `stance_from_official(gov_sources) -> list[dict]` — 각 `{"actor": ministry_of(title+excerpt), "actor_type":"government", "position", "basis":"official", "evidence": claim_summary or title, "url", "source_id", "at"}`; `position`이 None이면 제외. 같은 actor는 최신 1건.
- Produces: `stance_from_vote(vote_source) -> list[dict]` — `party_breakdown` 상위 4정당, `{"actor": party, "actor_type":"party", "position": {"yes":n,"no":n,"abstain":n}, "basis":"vote", ...}`. 합계 0인 정당·빈 이름 제외.
- Produces: `bias_from_meta(article_meta: dict) -> dict` → `{"left","center","right","foreign","unknown"}` (`official`은 `unknown`에 합산).
- Produces: `rank_score(issue: dict, counts: dict, last_activity_at: str, now: datetime) -> float` — 수동 +1000, 뉴스 `min(newsworthiness,20)`, 표결 +6/법안 +3/정부 +2, 72h 반감 감쇠, 상한 40(수동 제외).
- Produces: `build_digest(issue, sources, now, press_stance: list|None = None) -> dict` — 스펙 §6.2 구조. `stance = official + vote + (press_stance or [])[:6]`. `last_activity_at = max(source.published_at, max(meta.at))`.

- [ ] **Step 1: 실패 테스트** (핵심 단언만 발췌, 각 함수 최소 1개 + Review Focus 1·4)

```python
from datetime import datetime, timezone
from utils.issue_digest import (count_sources, representative_vote, stance_from_vote, stance_from_official, bias_from_meta, rank_score, build_digest, ministry_of)
VOTE = {"id":"v1","type":"assembly_vote","title":"표결: 국민연금법","published_at":"2026-11-08","vote":{"yes":193,"no":40,"abstain":6,"result":"가결","party_breakdown":{"더불어민주당":{"yes":160,"no":0,"abstain":1},"무소속":{"yes":0,"no":0,"abstain":0}}}}
def test_counts(): assert count_sources([VOTE,{"type":"gov_policy"}]) == {"gov":1,"bill":0,"vote":1}
def test_rep_vote_latest():
    older = {**VOTE, "id":"v0", "published_at":"2026-01-01"}
    assert representative_vote([older, VOTE])["source_id"] == "v1"
def test_vote_stance_skips_empty_party():
    rows = stance_from_vote(VOTE); assert [r["actor"] for r in rows] == ["더불어민주당"]; assert rows[0]["basis"] == "vote"
def test_official_requires_position():
    assert stance_from_official([{"id":"g","type":"gov_policy","title":"기획재정부, 추경 집행","position":None}]) == []
def test_ministry(): assert ministry_of("기획재정부는 오늘") == "기획재정부"; assert ministry_of("아무 말") == "정부"
def test_bias_merges_official_into_unknown():
    assert bias_from_meta({"a":{"leaning":"official"},"b":{"leaning":"left"}}) == {"left":1,"center":0,"right":0,"foreign":0,"unknown":1}
def test_rank_caps_and_decays():
    now = datetime(2026,11,10,tzinfo=timezone.utc)
    fresh = rank_score({"auto_generated":True,"newsworthiness":99}, {"gov":1,"bill":1,"vote":1}, "2026-11-10T00:00:00+00:00", now)
    old = rank_score({"auto_generated":True,"newsworthiness":99}, {"gov":1,"bill":1,"vote":1}, "2026-11-01T00:00:00+00:00", now)
    assert fresh <= 40 and old < fresh
    assert rank_score({"auto_generated":False}, {"gov":0,"bill":0,"vote":0}, "2026-11-10T00:00:00+00:00", now) >= 1000
def test_build_digest_shape():
    d = build_digest({"auto_generated":True,"newsworthiness":5,"article_meta":{"a":{"leaning":"left","at":"2026-11-09T00:00:00+00:00"}}}, [VOTE], datetime(2026,11,10,tzinfo=timezone.utc))
    assert d["counts"]["media"] == 1 and d["has_vote"] and d["vote"]["yes"] == 193 and d["stance"][0]["basis"] == "vote" and "rank" in d
```

- [ ] **Step 2: 실패 확인** → **Step 3: 구현**(`utils/ministries.py`는 중앙행정기관 명칭 리스트 상수 `MINISTRIES`, 긴 이름 우선 정렬) → **Step 4: 통과 확인**
- [ ] **Step 5: 커밋** `feat(digest): pure digest computation (counts, stance, bias, rank)`

### Task 6: 입장 추출과 요약 재생성 규칙

**Files:**
- Modify: `utils/gemini_rest.py`(프롬프트·함수 추가), `services/news_issue_service.py:135-165`(`summarize_pending_issues`)
- Create: `tests/test_stance_parse.py`

**Interfaces:**
- Produces: `extract_stances(title: str, snippets: list[str]) -> tuple[list[dict]|None, str|None]` — JSON 배열 `[{actor, position, evidence, article_index}]`, `position ∈ {support, oppose, criticize, propose, explain, neutral}`, 최대 4. `kind="stance"`. 예산 종류별 한도가 0이라 기본 운영에서는 호출되지 않는다(`STANCE_PRESS=1`이면 `per_kind["stance"]=4`).
- Produces: `utils/fallback_summary.py`: `fallback_summary(issue: dict, articles_by_id: dict[str, dict]) -> str` — 뉴스 이슈: `article_meta`에서 `leaning == "center"`인 최신 기사 제목, 없으면 최신 기사 제목, 기사가 없으면 제목 그대로. 법안 이슈: `"{law_name} · {status} · {M.D}"`. 빈 문자열을 돌려주지 않는다.
- Produces: `parse_stances(obj, snippets) -> list[dict]` (순수, `gemini_rest`에서 분리해 테스트) — 유효하지 않은 항목 제거, `basis="press"`, `evidence`에 해당 스니펫 제목.
- Modifies: `summarize_pending_issues(limit=10)` — 대상 = `auto_generated`이고 (`ai_summarized` 거짓 **또는** `evidence_hash`가 저장값과 다르고 기사 수가 5건 이상 늘었을 때)인 이슈, `digest.rank` 내림차순(없으면 `newsworthiness`). 성공 시 `summary`, `ai_summarized=True`, `evidence_hash` 저장. 예산 거부(`budget`)가 나오면 즉시 중단. 생성·갱신 경로의 `summary`는 `ai_summarized`가 거짓일 때만 `fallback_summary`로 덮는다(Task 8에서 쓰기 경로 수정).

- [ ] **Step 1: 실패 테스트**

```python
from utils.gemini_rest import parse_stances
SN = ["민주당 “추경 즉시 처리” — ...", "국민의힘 “현금 살포” 비판 — ..."]
def test_parse_filters_bad_position():
    out = parse_stances([{"actor":"민주당","position":"support","evidence":"즉시 처리","article_index":0},{"actor":"x","position":"meh","evidence":"","article_index":1}], SN)
    assert len(out) == 1 and out[0]["basis"] == "press" and out[0]["actor"] == "민주당"
def test_parse_caps_four():
    rows = [{"actor":f"a{i}","position":"neutral","evidence":"e","article_index":0} for i in range(6)]
    assert len(parse_stances(rows, SN)) == 4

# tests/test_fallback_summary.py
from utils.fallback_summary import fallback_summary
def test_news_prefers_center_latest():
    iss = {"auto_key":"news:1","title":"t","article_meta":{"a":{"leaning":"left","at":"2026-11-10"},"b":{"leaning":"center","at":"2026-11-09"}}}
    arts = {"a":{"title":"한겨레 제목"},"b":{"title":"연합 제목"}}
    assert fallback_summary(iss, arts) == "연합 제목"
def test_news_without_center_uses_latest():
    iss = {"auto_key":"news:1","title":"t","article_meta":{"a":{"leaning":"left","at":"2026-11-10"},"b":{"leaning":"right","at":"2026-11-09"}}}
    assert fallback_summary(iss, {"a":{"title":"A"},"b":{"title":"B"}}) == "A"
def test_bill_format():
    assert fallback_summary({"auto_key":"bill:1","law_name":"국민연금법","status":"가결","updated_at":"2026-11-08"}, {}) == "국민연금법 · 가결 · 11.8"
def test_never_empty():
    assert fallback_summary({"auto_key":"news:1","title":"제목만"}, {}) == "제목만"
```

- [ ] **Step 2: 실패 확인** → **Step 3: 구현**(`_STANCE_PROMPT`: "행위자(정당·부처·인물)별 입장을 근거 인용과 함께 JSON 배열로", temperature 0) → **Step 4: 통과 확인**
- [ ] **Step 5: `fallback_summary` 구현, `summarize_pending_issues` 수정**(근거 해시 비교, `limit=10`, 스니펫은 `article_ids[:8]`을 `get_all` 1회로, 예산 거부 시 중단)
- [ ] **Step 6: 커밋** `feat(ai): budgeted summaries, rule-based fallback summary, optional press stance`

### Task 7: digest 갱신 서비스와 목록 API v2

**Files:**
- Create: `services/issue_digest_service.py`, `firestore.indexes.json`, `tests/test_issue_list_query.py`
- Modify: `services/issue_service.py:37-54`(`list_summaries`), `routers/issue_router.py:17-19`, `utils/issue_rules.py:4`(`SUMMARY_KEYS`에 `digest` 추가), `scripts/backfill_issues.py`(`digest` 서브커맨드)

**Interfaces:**
- Produces: `IssueDigestService.refresh(issue_ids: list[str]|None, sources_by_issue: dict[str, list[dict]]|None, press: bool = False) -> dict` — 지정 이슈(없으면 `active != false` 전체)의 `digest`를 Task 5 `build_digest`로 계산해 **값이 바뀐 문서만** `update`. `sources_by_issue`가 없으면 `source_items`를 `issue_ids array_contains_any`(10개 단위) 또는 `issue_id in`으로 묶어 조회. `press=True`(`STANCE_PRESS=1`)일 때만 official·vote가 비고 `counts.media >= 5`이며 `stance_state != "done"`이고 해시가 바뀐 이슈에 한해 `extract_stances` 호출(예산이 허용하는 만큼), 결과를 `press_stance`·`stance_state`에 저장.
- Produces: `IssueService.list_summaries(status, category, limit, offset, v=None, sort="rank", filter=None, cursor=None)` — `v == 2`일 때: Firestore `where("active","==",True)` + 필터(`has_official`/`has_vote`/`has_gov` → `digest.<f> == True`, `status`) + `order_by(sort_field desc, "id")` + 커서 `start_after` + `limit+1`로 `next_cursor` 산출. 반환 `{"items": [...to_summary + digest], "next_cursor": str|None}`. `v`가 없으면 기존 동작(리스트) 유지.
- Produces: 순수 `utils/issue_list_query.py: build_query_plan(sort, filter) -> dict` → `{"order": "digest.rank"|"digest.last_activity_at"|"digest.counts.media", "where": [("digest.has_vote","==",True)]...}`; 알 수 없는 값은 기본.
- Produces: `firestore.indexes.json` — `active` × (필터 4종 + 없음) × 정렬 3종 복합 인덱스 15개.

- [ ] **Step 1: 실패 테스트**

```python
from utils.issue_list_query import build_query_plan
def test_default_plan(): assert build_query_plan(None, None) == {"order": "digest.rank", "where": [("active","==",True)]}
def test_filter_vote(): assert ("digest.has_vote","==",True) in build_query_plan("updated","has_vote")["where"]
def test_unknown_sort_falls_back(): assert build_query_plan("zzz", None)["order"] == "digest.rank"
def test_status_filter(): assert ("status","==","가결") in build_query_plan(None,"status:가결")["where"]
```

- [ ] **Step 2: 실패 확인** → **Step 3: 구현** → **Step 4: 통과 확인**
- [ ] **Step 5: `IssueDigestService.refresh` 구현** 및 `backfill_issues.py digest` 서브커맨드(전체 이슈, `press=False`, `active`가 없는 문서는 `active=True`를 함께 기록).
- [ ] **Step 6: `list_summaries` v2 분기와 라우터 파라미터(`v: int|None, sort: str = "rank", filter: str|None, cursor: str|None`) 추가.** 깨진 커서는 첫 페이지.
- [ ] **Step 7: `firestore.indexes.json` 작성**, 배포 명령을 파일 머리 주석에 적는다: `firebase deploy --only firestore:indexes --project koreanpolitical`.
- [ ] **Step 8: 커밋** `feat(issues): digest refresh service, list API v2 with server sort/filter/cursor, indexes`

### Task 8: 뉴스 이슈 중복 방지와 병합 스크립트

**Files:**
- Create: `utils/issue_merge.py`, `tests/test_issue_merge.py`, `scripts/merge_duplicate_issues.py`
- Modify: `services/news_issue_service.py:40-47`(`_title`), `:77-97`, `:113-123`

**Interfaces:**
- Produces: `top_person(members: list[dict]) -> str|None` — `entities.people` 빈도 1위.
- Produces: `clean_title(name: str|None, phrase: str) -> str` — 인용구에서 이름 제거 후 기존 포맷.
- Produces: `should_merge(cluster: dict, issue: dict, now: datetime) -> bool` — `cluster = {"article_ids", "person", "phrases"}`, 조건: 같은 `person` **and** `issue.digest.last_activity_at`(없으면 `updated_at`) 14일 이내 **and** (`overlap >= 0.3`(분모=작은 집합) **or** 인용구 포함(4자 이상)).
- Produces: `merge_plan(issues: list[dict], now) -> list[tuple[str, str]]` — `(흡수될 id, 남을 id)` 쌍, 가장 오래된 `started_at`이 남는다, 이미 `merged_into` 있는 문서 제외, 한 문서는 한 번만.
- Produces: `scripts/merge_duplicate_issues.py [--apply] [--report out.md]` — dry-run이 병합 쌍 표(제목 A → 제목 B, 사유)를 출력·저장. `--apply`: 백업 덤프 → 남는 문서에 `article_ids`·`article_meta`·`events` 합집합(`sorted_article_ids`), 흡수 문서에 `merged_into`, `active=False` → 흡수 문서를 가리키는 `source_items.links`·`issue_ids`·`issue_id`를 남는 id로 치환.

- [ ] **Step 1: 실패 테스트**

```python
from datetime import datetime, timezone
from utils.issue_merge import top_person, clean_title, should_merge, merge_plan
NOW = datetime(2026,11,10,tzinfo=timezone.utc)
def test_top_person(): assert top_person([{"entities":{"people":["권영진","정점식"]}},{"entities":{"people":["권영진"]}}]) == "권영진"
def test_clean_title_strips_name(): assert clean_title("김승원", "김승원 공세") == "김승원 ‘공세’"
def test_merge_requires_same_person():
    c = {"article_ids":{"a","b","c"},"person":"권영진","phrases":["멱살 파문"]}
    iss = {"entities":{"people":["김승원"]},"article_ids":["a","b","c"],"keywords":["멱살"],"updated_at":"2026-11-09T00:00:00+00:00"}
    assert not should_merge(c, iss, NOW)
def test_merge_by_phrase_containment():
    c = {"article_ids":{"x"},"person":"권영진","phrases":["멱살 파문"]}
    iss = {"entities":{"people":["권영진"]},"article_ids":["a"],"keywords":["멱살"],"updated_at":"2026-11-09T00:00:00+00:00"}
    assert not should_merge(c, iss, NOW)  # '멱살'은 3자 → 포함 조건 불충족
    iss["keywords"] = ["멱살 파문 징계"]
    assert should_merge(c, iss, NOW)
def test_merge_stale_issue_not_merged():
    c = {"article_ids":{"a","b"},"person":"권영진","phrases":["멱살 파문"]}
    iss = {"entities":{"people":["권영진"]},"article_ids":["a","b"],"keywords":["멱살 파문"],"updated_at":"2026-01-01T00:00:00+00:00"}
    assert not should_merge(c, iss, NOW)
def test_merge_plan_keeps_oldest_once():
    a = {"id":"a","started_at":"2026-10-01","entities":{"people":["권영진"]},"article_ids":["1","2","3"],"keywords":["멱살 파문"],"updated_at":"2026-11-09"}
    b = {"id":"b","started_at":"2026-10-05","entities":{"people":["권영진"]},"article_ids":["1","2"],"keywords":["멱살 파문 징계"],"updated_at":"2026-11-09"}
    assert merge_plan([b, a], NOW) == [("b","a")]
```

- [ ] **Step 2: 실패 확인** → **Step 3: 구현** → **Step 4: 통과 확인**
- [ ] **Step 5: `generate_news_issues` 수정** — 기존 대조 루프에서 `news:` 건너뛰기 제거, 뉴스 이슈에는 `should_merge`로 판정. 제목은 `clean_title(top_person(members), rep)`. 갱신 패치에서 `summary` 제거(단 `ai_summarized`가 거짓이면 `fallback_summary`로 갱신), 신규 문서는 `summary=fallback_summary(...)`, `ai_summarized=False`, `active=True`. 동일 수정 `issue_cluster_service.py:102-104`(법안 이슈는 `fallback_summary`의 법안 형식).
- [ ] **Step 6: `backfill_issues.py summary-flags` 서브커맨드 추가**(템플릿 패턴 "여러 매체가 보도한 현안입니다"/"관련 정부·국회 1차 소스를 묶은 이슈입니다"인 이슈의 `summary`를 `fallback_summary`로 교체하고 `ai_summarized=False`; 기사 제목은 `article_ids[:5]` `get_all`) → **`scripts/merge_duplicate_issues.py` 구현**, dry-run 실행 — Run: `.venv/bin/python scripts/merge_duplicate_issues.py --report /tmp/merge-report.md` → 쌍 목록 출력. **적용은 사용자 확인 후.**
- [ ] **Step 7: 커밋** `feat(issues): dedupe news issues on create; merge script with dry-run`

### Task 9: 크로스링크 정제와 관계별 링크(다대다)

**Files:**
- Create: `utils/crosslink_match.py`, `tests/test_crosslink_match.py`, `utils/source_links.py`, `tests/test_source_links.py`
- Modify: `services/source_link_service.py`(crosslink·review·link_unlinked), `services/issue_cluster_service.py:112-117`, `services/issue_service.py`(get_detail 소스 조회), `scripts/backfill_issues.py`(`links` 서브커맨드)

**Interfaces:**
- Produces: `article_matches_issue(blob: str, issue: dict) -> bool` — 뉴스 이슈(`auto_key` `news:`): 인용구(`keywords[0]`) 전체 포함 **또는** 인용구 토큰(2자 이상, 불용어 제외) 2개 이상 포함. 인명 단독 불가. 법안·수동 이슈: 기존 `terms`(law_name·키워드 3자 이상) 포함.
- Produces: `add_link(source: dict, issue_id: str, status: str, score: float, reason: str, at: str) -> dict` — `links` 배열 갱신(같은 issue_id는 교체, `rejected`는 보존), `issue_ids` = status∈{auto,confirmed}인 id 목록, `issue_id`/`link_status`는 첫 링크 미러.
- Produces: `has_link(source, issue_id) -> bool`, `is_rejected(source, issue_id) -> bool`.
- Produces: `news_issue_link_score(source: dict, issue_blob: str, people: list[str]) -> tuple[float, str|None]` — `law_name`(4자↑) 또는 `bill.bill_name` 전체 포함 → `(12.0, "auto")`; `bill.proposers ∩ people` → `(5.0, "pending")`; 그 외 `(0, None)`.
- Modifies: `SourceLinkService.link_news_issues(days: int = 14, limit: int = 300) -> dict` — `published_at >= (KST 오늘-14일)` 소스를 커서로 읽고(`order_by published_at`), 활성 뉴스 이슈 각각의 `blob`(제목+요약+기사 제목 상위 30=`article_meta` 키 순 제목은 없음 → **이슈 `keywords`+`title`+`summary`**만 사용; 기사 제목 합본은 비용 때문에 쓰지 않는다)과 점수 계산, 미거절·미연결이면 `add_link`.
- Modifies: `review(source_id, action, issue_id)` — 관계 단위(`issue_id` 필수)로 `confirmed`/`rejected`.
- Modifies: `get_detail` 소스 조회 → `issue_ids array_contains`.
- Modifies: `generate_bill_issues` 소스 연결 → `add_link(..., "auto", 12, "bill_cluster")`.

- [ ] **Step 1: 실패 테스트**

```python
from utils.crosslink_match import article_matches_issue
NEWS = {"auto_key":"news:1","keywords":["멱살 파문","권영진"],"title":"권영진 ‘멱살 파문’"}
def test_name_only_not_enough(): assert not article_matches_issue("권영진 의원 지역구 행사 참석", NEWS)
def test_phrase_full_match(): assert article_matches_issue("국민의힘 멱살 파문 징계 착수", NEWS)
def test_two_tokens_match(): assert article_matches_issue("멱살 잡은 파문 확산", NEWS)
def test_bill_issue_uses_law_name(): assert article_matches_issue("국민연금법 개정안 통과", {"auto_key":"bill:1","law_name":"국민연금법","keywords":["국민연금법"]})

from utils.source_links import add_link, has_link, is_rejected, news_issue_link_score
def test_add_link_updates_mirrors():
    s = add_link({"id":"s"}, "i1", "auto", 12.0, "law_name", "2026-11-10")
    assert s["issue_ids"] == ["i1"] and s["issue_id"] == "i1" and s["link_status"] == "auto"
def test_rejected_not_in_issue_ids():
    s = add_link({"id":"s"}, "i1", "rejected", 0, "manual", "t"); assert s["issue_ids"] == [] and is_rejected(s, "i1")
def test_score_exact_law_name(): assert news_issue_link_score({"law_name":"국민연금법","bill":{"bill_name":"국민연금법 일부개정법률안","proposers":[]}}, "국민연금법 개정 논란", []) == (12.0, "auto")
def test_score_proposer_pending(): assert news_issue_link_score({"law_name":"xx","bill":{"bill_name":"yy","proposers":["김승원"]}}, "무관", ["김승원"]) == (5.0, "pending")
def test_score_short_law_name_ignored(): assert news_issue_link_score({"law_name":"형법","bill":None}, "형법 개정", []) == (0, None)
```

- [ ] **Step 2: 실패 확인** → **Step 3: 구현** → **Step 4: 통과 확인**
- [ ] **Step 5: 서비스 수정 4곳**(crosslink 기사 매칭 교체, `link_news_issues` 신설, review 관계화, bill 클러스터 `add_link`), `get_detail` 조회 교체(`issue_id ==` 결과와 합집합 유지).
- [ ] **Step 6: `backfill_issues.py links` 서브커맨드** — 기존 `issue_id`+`link_status`를 `links`/`issue_ids`로 변환(source_items 전체 1회 읽기, 변경 문서만 쓰기).
- [ ] **Step 7: 자동 연결 표본 보고** — Run: `.venv/bin/python -c "import asyncio; from services.source_link_service import source_link_service as s; print(asyncio.run(s.link_news_issues(dry_run=True)))"` (`dry_run` 파라미터는 후보 `(source title, issue title, score)` 20건 출력만) → 결과를 PR 설명에 첨부. **활성화는 정밀도 확인 후.**
- [ ] **Step 8: 커밋** `feat(links): per-relation source links, exact-match news linking, crosslink tightening`

### Task 10: 의원 표결 → 이슈 연결

**Files:**
- Create: `utils/member_issue_link.py`, `tests/test_member_issue_link.py`
- Modify: `services/member_service.py:51-61`(`get_member`)

**Interfaces:**
- Produces: `bill_issue_ids(votes: list[dict]) -> dict[str, str]` — `bill_id → "issue_bill_{canonical_bill_id}"` (`utils.bill_cluster.canonical_bill_id` 사용).
- Produces: `attach_issue_ids(votes, existing_issue_ids: set[str], manual_by_bill: dict[str, str]) -> list[dict]` — 각 표결에 `issue_id`(수동 우선, 없으면 존재하는 법안 이슈, 없으면 None).
- Modifies: `get_member` — `votes`가 있으면 `get_all`로 법안 이슈 존재 확인 1회 + `source_items.where("vote.bill_id","in", bids[:30])` 1회로 수동 링크 조회, `votes[].issue_id` 채움. `def`로 전환.

- [ ] **Step 1: 실패 테스트**

```python
from utils.member_issue_link import bill_issue_ids, attach_issue_ids
V = [{"bill_id":"PRC_X1","bill":"국민연금법","vote":"찬성"}]
def test_ids(): assert bill_issue_ids(V) == {"PRC_X1": "issue_bill_" + __import__("utils.bill_cluster", fromlist=["canonical_bill_id"]).canonical_bill_id("PRC_X1")}
def test_manual_preferred():
    out = attach_issue_ids(V, {"issue_bill_PRC_X1"}, {"PRC_X1": "manual1"}); assert out[0]["issue_id"] == "manual1"
def test_none_when_absent(): assert attach_issue_ids(V, set(), {})[0]["issue_id"] is None
```

- [ ] **Step 2: 실패 확인** → **Step 3: 구현** → **Step 4: 통과 확인** → **Step 5: `get_member` 수정** → **Step 6: 커밋** `feat(members): attach issue ids to member votes`

### Task 11: 판(edition) 문서와 오늘 API

**Files:**
- Create: `utils/edition.py`, `tests/test_edition.py`, `services/edition_service.py`, `routers/today_router.py`
- Modify: `main.py:64`(라우터 등록 `prefix="/api/today"`)

**Interfaces:**
- Produces: `kst_date(ts: str|None) -> str|None` — ISO UTC 또는 `YYYY-MM-DD`(그대로) → KST `YYYY-MM-DD`; 파싱 실패·빈 값은 None.
- Produces: `select_top_issues(issues: list[dict], date: str, n=3) -> list[dict]` — `kst_date(digest.last_activity_at) == date`인 `active` 이슈를 `digest.rank` 내림차순 상위 n, 스냅샷 필드 `{id,title,summary,status,category,counts,vote,stance(official|vote만)}`.
- Produces: `build_edition(date, issues, sources, overview) -> dict` — `{"date","top_issues","assembly":{"votes":[...],"bills":[...]},"government":[...],"other_issue_ids":[...],"overview","built_at"}`. 소스 항목은 `{id,title,law_name,published_at,procedural,issue_ids,vote?}`.
- Produces: `EditionService.build(date: str|None = None, issues=None, sources=None) -> dict` — 인자가 없으면 KST 오늘, 활성 이슈 전체(`digest` 포함)와 그날 소스(`published_at` 접두 비교는 불가하므로 **최근 3일 소스를 `published_at >=` 로 읽고 `kst_date`로 필터**)를 읽어 `editions/{date}` upsert. **`date`가 오늘이 아니면 쓰지 않고 예외.**
- Produces: `EditionService.get(date: str) -> dict|None` — 판 1회 읽기 + `other_issue_ids` `get_all` → 응답 `{"edition": {...}, "other_issues": [to_summary+digest]}`.
- Produces: `GET /api/today?date=YYYY-MM-DD`(`def`) — 판 없으면 `data.edition = None`, `data.other_issues = []`, 200. 날짜 형식 오류 400.

- [ ] **Step 1: 실패 테스트**

```python
from utils.edition import kst_date, select_top_issues, build_edition
def test_kst_date_iso(): assert kst_date("2026-11-09T16:30:00Z") == "2026-11-10"
def test_kst_date_plain(): assert kst_date("2026-11-10") == "2026-11-10"
def test_kst_date_bad(): assert kst_date("") is None and kst_date("nope") is None
def test_top_issues_by_rank_same_day():
    iss = [{"id":"a","active":True,"digest":{"rank":5,"last_activity_at":"2026-11-10T01:00:00+00:00","counts":{},"stance":[{"basis":"press"}]}},
           {"id":"b","active":True,"digest":{"rank":9,"last_activity_at":"2026-11-10T02:00:00+00:00","counts":{},"stance":[]}},
           {"id":"c","active":True,"digest":{"rank":99,"last_activity_at":"2026-11-01T02:00:00+00:00","counts":{}}}]
    top = select_top_issues(iss, "2026-11-10"); assert [t["id"] for t in top] == ["b","a"]; assert top[1]["stance"] == []
def test_build_edition_sections():
    e = build_edition("2026-11-10", [], [{"id":"v","type":"assembly_vote","published_at":"2026-11-10","title":"표결: X","law_name":"X","procedural":False,"issue_ids":[],"vote":{"yes":1,"no":0,"abstain":0}},{"id":"g","type":"gov_policy","published_at":"2026-11-10T03:00:00Z","title":"브리핑","issue_ids":[]},{"id":"old","type":"gov_policy","published_at":"2026-11-01T03:00:00Z","title":"x","issue_ids":[]}], None)
    assert len(e["assembly"]["votes"]) == 1 and len(e["government"]) == 1 and e["overview"] is None
```

- [ ] **Step 2: 실패 확인** → **Step 3: 구현** → **Step 4: 통과 확인**
- [ ] **Step 5: 서비스·라우터 구현**, `main.py` 등록, 캐시 헤더 적용.
- [ ] **Step 6: 커밋** `feat(today): daily edition documents and /api/today`

### Task 12: 공개 소스 목록 API

**Files:**
- Create: `services/source_list_service.py`
- Modify: `routers/source_router.py`(`GET ""` 추가, 공개)

**Interfaces:**
- Produces: `GET /api/sources?type=assembly_vote|assembly_bill|gov_policy&cursor=&limit=30`(`def`) — `order_by("published_at", desc), order_by("id")` + `start_after` 커서(`{"p": published_at, "i": id}`), 응답 `{"items": [{id,type,title,law_name,published_at,procedural,url,issue_ids,vote?}], "next_cursor"}`. `type` 누락·오류는 400. 캐시 헤더 적용.

- [ ] **Step 1: 라우트 테스트(TestClient + monkeypatch, `tests/test_share_router.py` 패턴)** — `tests/test_source_list_router.py`: 서비스 함수를 가짜로 바꿔 `type` 누락 400, 정상 200과 `next_cursor` 키 존재 단언.
- [ ] **Step 2: 실패 확인** → **Step 3: 구현** → **Step 4: 통과 확인** → **Step 5: 커밋** `feat(sources): public paginated source list`

### Task 13: 파이프라인 단일 진입점·계측·워크플로

**Files:**
- Create: `scripts/run_pipeline.py`, `utils/read_meter.py`, `tests/test_read_meter.py`
- Modify: `.github/workflows/news-collect.yml`(두 번째 step의 heredoc → `python scripts/run_pipeline.py`), `routers/source_router.py:18-44`(`_run_pipeline`이 같은 함수를 호출)

**Interfaces:**
- Produces: `class ReadMeter` with `install(db_module) -> None`(firestore `DocumentReference.get`, `Query.stream`, `Client.get_all`, `DocumentReference.set/update` 래핑), `snapshot() -> dict` `{"reads","writes"}`, `reset()`.
- Produces: `class PipelineContext` (`services/pipeline_context.py`) — 지연 로더 `articles(limit=400)`, `active_issues()`, `recent_sources(days=14)`, `member_names()`, 각각 첫 호출만 Firestore를 읽고 이후 캐시 반환; `mark_issue_changed(issue_id)`, `changed_issue_ids`. 기존 서비스 메서드는 선택 인자 `ctx: PipelineContext|None = None`을 받아 있으면 캐시를 쓴다(없으면 기존 동작).
- Produces: `run_pipeline(steps: list[str]|None = None, heavy: bool|None = None) -> dict`. `heavy`가 None이면 KST 현재 시각 `hour % 3 == 0`일 때만 무거운 단계 실행. 가벼운 단계(매시): `collect_news`. 무거운 단계(3시간마다): `ingest_gov → ingest_bills → ingest_votes → enrich_pending → generate_bill_issues → link_unlinked → crosslink → generate_news_issues → link_news_issues → summarize_pending_issues → refresh_digest(changed) → build_edition → enrich_member_bills → enrich_member_votes`. 모든 단계가 같은 `ctx`를 공유한다. 끝에 `[meter] reads=N writes=N gemini=N` 출력, `reads > 2000`이면 경고 줄.
- Modifies: 워크플로 env에 `GEMINI_DAILY_BUDGET: "18"`, `STANCE_PRESS: "0"` 추가.

- [ ] **Step 1: 실패 테스트** — `tests/test_read_meter.py`: 가짜 클래스에 `install`한 뒤 `get()` 2회·`update()` 1회 호출하면 `snapshot() == {"reads": 2, "writes": 1}`.
- [ ] **Step 2: 실패 확인** → **Step 3: 구현** → **Step 4: 통과 확인**
- [ ] **Step 5: `PipelineContext` 구현, 서비스 6곳(`generate_bill_issues`, `link_unlinked`, `crosslink`, `generate_news_issues`, `link_news_issues`, `refresh`)에 `ctx` 인자 추가.** 테스트: `tests/test_pipeline_context.py` — 가짜 로더로 `articles()` 2회 호출 시 로더는 1회만 실행.
- [ ] **Step 6: `run_pipeline.py`와 워크플로 수정, `_run_pipeline` 위임.**
- [ ] **Step 7: 로컬 무거운 실행 1회** — Run: `.venv/bin/python scripts/run_pipeline.py --heavy` → 마지막 줄 `[meter] reads=` 값 **2,000 이하** 확인. 넘으면 로더 공유 누락을 찾아 고친 뒤 재측정. 결과를 PR 설명에 기록.
- [ ] **Step 8: 커밋** `chore(pipeline): shared context, 3-hour heavy cadence, read/write/gemini metering`

### Task 14: 1차 배포·backfill·정제·2차 배포(운영 절차)

**Files:** 없음(절차). 결과는 PR 설명과 `docs/superpowers/plans/2026-11-10-issue-first-backend.md` 하단 "실행 기록"에 남긴다.

- [ ] **Step 1: 선행 확인** — 없음(무료 유지). 기존 `GOOGLE_API_KEY`를 그대로 쓴다. 배포 전 `GEMINI_DAILY_BUDGET=18`, `STANCE_PRESS=0`을 Vercel env와 GH 시크릿/워크플로 env에 반영.
- [ ] **Step 2: 1차 배포** — PR 머지 후 `cd politics_backend && vercel --prod --yes`. 확인: `curl -s -o /dev/null -w "%{http_code} %{time_total}\n" https://politicsbackend-ruby.vercel.app/api/issues/609c190844a5417c87695945e7bef25e` 2회(콜드·웜) 기록, 구 응답 필드 존재 확인(`source_panels.government`, `perspectives`, `articles`).
- [ ] **Step 3: 인덱스 배포** — `firebase deploy --only firestore:indexes --project koreanpolitical` (빌드 완료까지 수 분, 콘솔 상태 확인).
- [ ] **Step 4: backfill** — `backfill_issues.py article-meta --apply` → `links --apply` → `digest --apply` → `summary-flags --apply`(템플릿 요약 이슈 `ai_summarized=False`). 각 dry-run 수치와 apply 수치 대조.
- [ ] **Step 5: 정제** — crosslink 규칙은 이미 배포됨. `merge_duplicate_issues.py --report` → **사용자에게 요약(쌍 수·예시 3개) 제시 → 확인 후** `--apply`. 자동 연결 표본 20건 보고 → 정밀도 ≥ 0.9이면 워크플로 env `LINK_NEWS_ISSUES=1`로 활성화(기본 비활성).
- [ ] **Step 6: 2차 확인** — `GET /api/issues?v=2&sort=rank&limit=5` 200·`next_cursor`, `GET /api/today` 200, `GET /api/sources?type=assembly_vote` 200. 상세 웜·캐시 미스 5회 p50 ≤ 2초 기록. 상위 20 이슈 중 공식 기록 붙은 이슈 수 before/after 기록. **24시간 뒤 Firebase 콘솔 사용량에서 일일 읽기 수가 5만 미만인지 확인**해 기록.
- [ ] **Step 7: 실행 기록을 이 문서 하단에 추가하고 커밋** `docs(plan): backend rollout record`

---

## 실행 기록

(배포·backfill·병합 수치를 여기에 기록)
