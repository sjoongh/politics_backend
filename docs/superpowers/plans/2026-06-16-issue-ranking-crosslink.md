# 이슈 사건성 랭킹 + 법안 교차연결 (v1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (inline). Steps `- [ ]`.

**Goal:** 절차적 대안법안 도배를 잡고(사건성 랭킹/감점), 법률명+의안번호로 gov/news를 법안 이슈에 연결해 4단 뷰를 채운다.

**Architecture:** 순수 로직(법률명 정규화·사건성 점수)은 pytest. 기존 source_items/issues에 필드 추가(새 컬렉션 없음). 식별자 먼저→랭킹 다음(codex). AI 0(규칙 기반). 설계: `docs/superpowers/specs/2026-06-16-issue-ranking-crosslink-design.md`.

**Tech:** FastAPI, Firestore, React. 작업 전 `git checkout -b feat/issue-ranking`.

**검증:** 순수 로직 `pytest`. 클러스터/연결은 라이브 DB로 실행 확인. 프론트 빌드+Playwright.

---

## Task 0: 브랜치
- [ ] `cd /Users/manager/side/politics_backend && git checkout -b feat/issue-ranking`

---

## Task 1: 법률명 정규화 (순수, TDD)
**Files:** Create `utils/law_name.py`, `tests/test_law_name.py`

- [ ] **Step 1: 테스트**
```python
from utils.law_name import normalize_law_name, is_procedural

def test_normalize_strips_procedural_terms():
    assert normalize_law_name("항공안전법 일부개정법률안(대안)(국토교통위원장)") == "항공안전법"
    assert normalize_law_name("국민연금법 전부개정법률안") == "국민연금법"
    assert normalize_law_name("청년기본소득에 관한 법률안") == "청년기본소득에 관한 법률"

def test_is_procedural():
    assert is_procedural("항공안전법 일부개정법률안(대안)(국토교통위원장)") is True
    assert is_procedural("기후위기 특별위원회 구성의 건(의장)") is True
    assert is_procedural("노란봉투법") is False
```
- [ ] **Step 2:** `pytest tests/test_law_name.py -q` → fail
- [ ] **Step 3: 구현** — `utils/law_name.py`
```python
"""법안 제목 정규화 순수 로직 (테스트 대상). 법률명 추출 + 절차안 판정."""
import re

# 제거할 절차어(접미/수식). 순서대로 적용.
_PROC_TERMS = ["일부개정법률안", "전부개정법률안", "일부개정안", "전부개정안",
               "제정법률안", "개정법률안", "법률안", "개정안", "제정안", "대안", "수정안"]
_PROC_FLAGS = ["대안", "위원장", "(의장)", "구성의 건", "위원 선임", "수정안"]
_PAREN = re.compile(r"\([^)]*\)")


def normalize_law_name(title):
    if not title:
        return ""
    t = _PAREN.sub("", title)            # 괄호 내용 제거
    t = t.replace("표결:", "")
    for term in _PROC_TERMS:
        t = t.replace(term, "")
    return re.sub(r"\s+", " ", t).strip()


def is_procedural(title):
    t = title or ""
    return any(f in t for f in _PROC_FLAGS)
```
- [ ] **Step 4:** `pytest tests/test_law_name.py -q` → pass
- [ ] **Step 5: Commit** `feat(rank): law name normalization + procedural flag (pure)`

---

## Task 2: 사건성 점수 (순수, TDD)
**Files:** Create `utils/newsworthiness.py`, `tests/test_newsworthiness.py`

- [ ] **Step 1: 테스트**
```python
from utils.newsworthiness import vote_contention, issue_score, PROMOTE

def test_contention_unanimous_is_zero():
    v = {"party_breakdown": {"A": {"yes": 5, "no": 0, "abstain": 0}}}
    assert vote_contention(v) == 0.0

def test_contention_cross_party_opposition_high():
    v = {"yes": 5, "no": 4, "abstain": 0,
         "party_breakdown": {"여당": {"yes": 5, "no": 0}, "야당": {"yes": 0, "no": 4}}}
    assert vote_contention(v) >= 0.5

def test_score_procedural_demoted():
    proc = issue_score({"procedural": True},
                       source_items=[{"type": "assembly_bill"}, {"type": "assembly_vote",
                       "vote": {"party_breakdown": {"A": {"yes": 3, "no": 0}}, "yes": 3, "no": 0}}],
                       article_count=0)
    hot = issue_score({"procedural": False},
                      source_items=[{"type": "assembly_vote",
                      "vote": {"yes": 5, "no": 4, "party_breakdown": {"여": {"yes": 5, "no": 0}, "야": {"yes": 0, "no": 4}}}}],
                      article_count=4)
    assert hot > proc
    assert proc < PROMOTE   # 절차안+무뉴스+만장일치 → 승격 미달
```
- [ ] **Step 2:** fail 확인
- [ ] **Step 3: 구현** — `utils/newsworthiness.py`
```python
"""이슈 사건성(newsworthiness) 점수 순수 로직 (테스트 대상)."""
PROMOTE = 3.0   # 이슈 노출 최소 점수


def vote_contention(vote):
    """표결 갈등도 0~1. 만장일치=0, 찬반 접전·교차당 반대=높음."""
    if not vote:
        return 0.0
    yes, no = vote.get("yes", 0), vote.get("no", 0)
    total = yes + no + vote.get("abstain", 0)
    if total == 0:
        return 0.0
    closeness = 1 - abs(yes - no) / total          # 접전일수록 1
    pb = vote.get("party_breakdown") or {}
    cross = 1.0 if any(p.get("no", 0) > 0 for p in pb.values()) and \
        any(p.get("yes", 0) > 0 for p in pb.values()) else 0.0
    return round(min(1.0, 0.6 * closeness + 0.4 * cross), 3)


def issue_score(issue, source_items, article_count=0):
    types = {s.get("type") for s in (source_items or [])}
    contention = max((vote_contention(s.get("vote")) for s in source_items
                      if s.get("type") == "assembly_vote"), default=0.0)
    gov_connected = 1 if "gov_policy" in types else 0
    score = (contention * 4
             + min(len(types), 4) * 1.5
             + min(article_count, 5) * 1.2
             + gov_connected * 2)
    # 절차안 + 무뉴스 + 무갈등 → 감점(대안법안 도배 해소)
    if issue.get("procedural") and article_count == 0 and contention == 0:
        score -= 5
    return round(score, 2)
```
- [ ] **Step 4:** pass 확인
- [ ] **Step 5: Commit** `feat(rank): newsworthiness scoring (pure, procedural penalty)`

---

## Task 3: 정규화를 source_item에 반영
**Files:** Modify `utils/source_item.py`(law_name·procedural 필드), `tests/test_source_item.py`

- [ ] **Step 1:** `normalize_bill`/`normalize_vote`에 `law_name = normalize_law_name(title)`, `procedural = is_procedural(title)` 추가. (gov_policy도 law_name 추출 시도.)
- [ ] **Step 2:** 테스트에 law_name/procedural 검증 1개 추가.
- [ ] **Step 3:** `pytest -q` 통과. **Commit** `feat(rank): tag source_items with law_name/procedural`

---

## Task 4: 절차성 감점 + 사건성 게이트(클러스터)
**Files:** Modify `services/issue_cluster_service.py`

- [ ] **Step 1:** 클러스터별로 `issue_score` 계산. 자동이슈 doc에 `law_name`, `procedural`, `newsworthiness` 저장.
- [ ] **Step 2: 노출 게이트** — score < PROMOTE 이고 패널(연결 소스 type 종류) < 2 이면 이슈 생성 보류(source_items는 link_status='new' 유지). 기존 자동이슈는 점수 갱신.
- [ ] **Step 3:** 라이브 실행 → 절차적 대안법안(만장일치·무뉴스) 다수가 보류되는지 확인. **Commit** `feat(rank): newsworthiness gate in bill clustering`

---

## Task 5: 법률명+의안번호 교차연결 (gov/news)
**Files:** Modify `services/source_link_service.py`(또는 신규 `services/crosslink_service.py`)

- [ ] **Step 1: 의안번호 우선 연결** — gov/news source_items의 entities.bills(의안번호)가 이슈 entities.bills와 겹치면 그 이슈에 연결(link_status='auto').
- [ ] **Step 2: 법률명 보조 연결** — 자동이슈의 `law_name`이 gov 제목 또는 news(title+ai_summary)에 등장 + 발행일이 이슈 표결일 −14~+7일 이내면 연결. 단 law_name 길이 ≥3, 약하면 pending.
- [ ] **Step 3: 뉴스 패널 채우기** — articles에서 law_name 매칭되는 기사를 이슈 `article_ids`에 추가(중복 방지).
- [ ] **Step 4:** 라이브 실행 → 한 법안 이슈에 정부/뉴스가 붙어 4단 패널 ≥2 채워지는지 확인. **Commit** `feat(rank): cross-link gov/news to bill issues by 의안번호/법률명`

---

## Task 6: 점수순 랭킹 API + 프론트
**Files:** Modify `services/issue_service.py`(list_summaries 정렬), `routers/issue_router.py`(필요시), 프론트 `useIssues`/이슈목록

- [ ] **Step 1:** `list_summaries`가 `newsworthiness` 내림차순 정렬(없으면 updated_at). 자동이슈 노출조건(score≥PROMOTE AND panels≥2) 필터.
- [ ] **Step 2:** 프론트 이슈 목록/홈에서 정렬 결과 그대로 노출. (선택) 사건성 낮은 이슈는 "기타 법안 활동" 접기 섹션.
- [ ] **Step 3:** 빌드 + Playwright로 라이브-스타일 캡처(절차안이 상위에서 밀려났는지). **Commit** `feat(rank): rank issue list by newsworthiness`

---

## Task 7: 최종 검증 + codex 리뷰 + 머지/배포
- [ ] **Step 1:** `pytest tests/ -q` 전체 통과 + 프론트 빌드
- [ ] **Step 2:** codex 코드 리뷰 → 반영
- [ ] **Step 3:** 라이브 e2e — 이슈목록 상위가 사건성순, 절차안 강등, 4단 패널 ≥2 확인(스크린샷)
- [ ] **Step 4:** main 머지 + Vercel/firebase 배포 + 수집 워크플로 1회 트리거

---

## Self-Review
- 스펙 항목(법률명 정규화·사건성 점수·절차감점·게이트·교차연결·랭킹) 전부 Task로 커버.
- Task1·2 TDD 실제 코드. 3~6 구체 + 라이브 검증.
- 가정: 법률명 과합침은 의안번호 우선+날짜창으로 완화(Task5), 약매칭 pending.
