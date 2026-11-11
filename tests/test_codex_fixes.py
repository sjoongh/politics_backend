"""codex 머지 전 리뷰 수정분 회귀 테스트."""
import asyncio
import threading
import services.source_link_service as lsvc
from services.pipeline_context import PipelineContext
from tests.test_issue_digest_service import WriteDB
from utils.ai_budget import AiBudget


# ---- 차단1: 예산은 원자적으로 예약된다(동시 요청이 한도를 넘지 못함)
class AtomicMem:
    def __init__(self):
        self.d, self.lock = {}, threading.Lock()
    def get(self): return dict(self.d)
    def set(self, v): self.d = dict(v)
    def atomic(self, fn):
        with self.lock:
            new, ok = fn(dict(self.d))
            if ok:
                self.d = dict(new)
            return ok


def test_budget_atomic_reservation_never_exceeds_limit():
    store = AtomicMem()
    store.d = {"date": "d", "used": 17, "by_kind": {"summary": 9}, "exhausted": False}
    results = []
    def worker():
        results.append(AiBudget(limit=18, today="d", store=store, per_kind={"summary": 10}).try_acquire("summary"))
    ts = [threading.Thread(target=worker) for _ in range(4)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert results.count(True) == 1 and store.d["used"] == 18


def test_budget_atomic_failure_denies():
    class Fail(AtomicMem):
        def atomic(self, fn): raise RuntimeError("commit failed")
    assert not AiBudget(limit=18, today="d", store=Fail(), per_kind={"summary": 10}).try_acquire("summary")


# ---- 차단2: 공유 ctx의 소스 객체가 단계 간에 갱신돼 뒤 단계가 앞 단계 연결을 덮어쓰지 않는다
def test_link_unlinked_updates_ctx_source_in_place(monkeypatch):
    src = {"id": "s1", "type": "gov_policy", "title": "추경 집행 계획", "link_status": "new", "published_at": "2026-11-10",
           "entities": {"bills": ["B1"], "parties": [], "people": []}}
    issue_a = {"id": "A", "title": "추경", "keywords": ["추경"], "entities": {"bills": ["B1"], "parties": []}, "active": True}
    db = WriteDB({"issues": {"A": dict(issue_a)}, "source_items": {"s1": dict(src)}, "articles": {}})
    monkeypatch.setattr(lsvc, "db", db)
    ctx = PipelineContext(load_articles=lambda n: [], load_issues=lambda: [dict(issue_a)],
                          load_sources=lambda d: [src], load_member_names=lambda: set())
    asyncio.run(lsvc.source_link_service.link_unlinked(ctx=ctx))
    shared = ctx.recent_sources(14)[0]
    assert shared is src and "A" in (shared.get("issue_ids") or [])


def test_crosslink_keeps_previous_links_on_shared_source(monkeypatch):
    src = {"id": "s1", "type": "gov_policy", "title": "국민연금법 시행 브리핑", "published_at": "2026-11-10",
           "entities": {"bills": ["B9"]}, "links": [{"issue_id": "A", "status": "auto", "score": 12, "reason": "x", "at": "t"}],
           "issue_ids": ["A"], "issue_id": "A", "link_status": "auto"}
    issue_b = {"id": "B", "title": "국민연금법", "law_name": "국민연금법", "keywords": ["국민연금법"], "entities": {"bills": ["B9"]},
               "auto_key": "bill:B9", "article_ids": [], "active": True}
    db = WriteDB({"issues": {"B": dict(issue_b)}, "source_items": {"s1": dict(src)}, "articles": {}})
    monkeypatch.setattr(lsvc, "db", db)
    ctx = PipelineContext(load_articles=lambda n: [], load_issues=lambda: [dict(issue_b)],
                          load_sources=lambda d: [src], load_member_names=lambda: set())
    asyncio.run(lsvc.source_link_service.crosslink(ctx=ctx))
    assert set(db.data["source_items"]["s1"]["issue_ids"]) == {"A", "B"}


# ---- 중요6: ctx 이슈 로더는 최근 활동 이슈만(누적 이슈 수에 비례하지 않음), digest 없으면 전수 폴백
def test_issue_loader_is_bounded_by_recent_activity():
    import inspect
    from services import pipeline_context
    src = inspect.getsource(pipeline_context.firestore_context).split("def li")[1].split("def ls")[0]
    assert 'digest.last_activity_at' in src and '">="' in src


# ---- 차단3: 병합 스크립트는 소스 이관 → digest → 흡수 표시 순서이고, 중단된 병합을 재개한다
def test_merge_script_marks_absorbed_last_and_repairs():
    import inspect
    import scripts.merge_duplicate_issues as m
    body = inspect.getsource(m.apply_pair)
    assert body.index("_move_sources") < body.index('"merged_into"')
    assert hasattr(m, "repair_orphans")
