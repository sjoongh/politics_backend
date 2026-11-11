"""최종 리뷰 수정분 회귀 테스트(C1, I1, I2, I3, I4, I6)."""
import asyncio
import services.issue_digest_service as dsvc
import services.news_issue_service as nsvc
import services.issue_service as isvc
from services.pipeline_context import PipelineContext
from tests.test_issue_digest_service import WriteDB
from utils.ai_budget import AiBudget
from utils.cursor import encode_cursor, decode_cursor


# ---- C1: 뉴스 이슈 생성이 ctx에 변경을 표시하고, refresh는 ctx에 없는 id도 읽어 digest를 만든다
def _ctx(issues, articles, sources=()):
    return PipelineContext(load_articles=lambda n: list(articles), load_issues=lambda: list(issues),
                           load_sources=lambda d: list(sources), load_member_names=lambda: {"권영진", "김승원"})


def test_news_issue_creation_marks_changed(monkeypatch):
    db = WriteDB({"issues": {}, "articles": {}, "source_items": {}})
    monkeypatch.setattr(nsvc, "db", db)
    arts = [{"id": f"a{i}", "title": f"권영진 ‘멱살 파문’ 논란 {i}", "ai_summary": "", "source": s,
             "published_at": "2026-11-10 01:00:00", "created_at": "2026-11-10T01:00:00+00:00"}
            for i, s in enumerate(["연합뉴스", "한겨레", "조선일보"])]
    ctx = _ctx([], arts)
    out = asyncio.run(nsvc.news_issue_service.generate_news_issues(ctx=ctx))
    assert out["success"] and out["data"]["created"] >= 1
    assert set(out["data"]["issue_ids"]) <= set(ctx.changed_issue_ids) and ctx.changed_issue_ids


def test_refresh_loads_ids_missing_from_ctx(monkeypatch):
    db = WriteDB({"issues": {"n1": {"auto_generated": True, "newsworthiness": 3, "auto_key": "news:1", "active": True, "article_meta": {}}},
                  "source_items": {}, "articles": {}})
    monkeypatch.setattr(dsvc, "db", db)
    ctx = _ctx([], [])          # ctx 이슈 목록은 비어 있음
    ctx.mark_issue_changed("n1")
    out = dsvc.issue_digest_service.refresh(ctx=ctx)
    assert out["data"]["updated"] == 1 and "digest" in db.data["issues"]["n1"]


# ---- I1: 공유 소스 로더는 최신순(DESC)으로 읽어 상한에 걸려도 최신 소스가 남는다
def test_firestore_context_source_loader_is_descending():
    import inspect
    from services import pipeline_context
    src = inspect.getsource(pipeline_context.firestore_context)
    assert "direction=_fs.Query.DESCENDING" in src.split("def ls")[1].split("def ln")[0]


# ---- I2: 수동 이슈 생성은 active·digest를 갖는다
def test_manual_create_has_active_and_digest(monkeypatch):
    from models.model import IssueSeed
    db = WriteDB({"issues": {}, "articles": {}, "source_items": {}})
    class R:
        def __init__(self, coll, _id): self.coll, self.id = coll, _id
        def set(self, d): db.data[self.coll][self.id] = dict(d)
        def get(self):
            from tests.test_issue_service_detail import Snap
            return Snap(self.id, db.data[self.coll].get(self.id))
        def update(self, p): db.data[self.coll][self.id].update(p)
    class C:
        def __init__(self, coll): self.coll = coll
        def document(self, _id): return R(self.coll, _id)
        def where(self, *a): return db.collection(self.coll).where(*a)
    class DB2:
        def collection(self, name): return C(name)
        def get_all(self, refs): return [r.get() for r in refs]
    monkeypatch.setattr(isvc, "db", DB2())
    out = asyncio.run(isvc.issue_service.create(IssueSeed(title="수동", summary="s", status="진행중", category="정치")))
    doc = db.data["issues"][out["data"]["id"]]
    assert doc["active"] is True and doc["digest"]["rank"] >= 1000


# ---- I3: 디코드는 되지만 조작된 커서는 첫 페이지로
def test_bad_cursor_values_fall_back_to_first_page():
    from utils.cursor import valid_page_cursor
    assert valid_page_cursor({"k": 1.5, "i": "abc"}, "k")
    assert not valid_page_cursor({"k": 1.5, "i": "a/b"}, "k")
    assert not valid_page_cursor({"k": 1.5, "i": 7}, "k")
    assert not valid_page_cursor({"k": [1], "i": "abc"}, "k")
    assert not valid_page_cursor({}, "k")


# ---- I4: cap 0 종류는 저장소를 읽지 않고 거부, 저장소 장애 시 거부
def test_zero_cap_kind_does_not_touch_store():
    class Boom:
        def get(self): raise AssertionError("store read")
        def set(self, v): raise AssertionError("store write")
    b = AiBudget(limit=18, today="d", store=Boom())
    assert not b.try_acquire("article")


def test_store_failure_denies():
    class Down:
        def get(self): raise RuntimeError("firestore down")
        def set(self, v): pass
    assert not AiBudget(limit=18, today="d", store=Down(), per_kind={"summary": 10}).try_acquire("summary")


# ---- I6: 결정적 id 문서가 이미 흡수된(merged_into) 경우 생존 문서에 쓴다
def test_deterministic_id_redirects_to_survivor(monkeypatch):
    import hashlib
    from utils.news_entities import normalize_phrase
    rep = "멱살 파문"
    key = hashlib.sha1(normalize_phrase(rep).encode()).hexdigest()[:14]
    dead_id = f"issue_news_{key}"
    db = WriteDB({"issues": {dead_id: {"merged_into": "keep", "active": False, "auto_key": f"news:{key}", "article_ids": []},
                             "keep": {"auto_generated": True, "auto_key": "news:k", "active": True, "article_ids": [], "article_meta": {},
                                      "entities": {"people": ["정점식"]}, "keywords": ["다른 사건"], "updated_at": "2026-01-01"}},
                  "articles": {}, "source_items": {}})
    monkeypatch.setattr(nsvc, "db", db)
    arts = [{"id": f"a{i}", "title": f"권영진 ‘멱살 파문’ {i}", "ai_summary": "", "source": s,
             "published_at": "2026-11-10 01:00:00", "created_at": "2026-11-10T01:00:00+00:00"}
            for i, s in enumerate(["연합뉴스", "한겨레"])]
    ctx = _ctx([db.data["issues"]["keep"] | {"id": "keep"}], arts)
    asyncio.run(nsvc.news_issue_service.generate_news_issues(ctx=ctx))
    assert db.data["issues"][dead_id].get("article_ids") == []            # 죽은 문서에 쓰지 않음
    assert len(db.data["issues"]["keep"].get("article_ids") or []) == 2   # 생존 문서로 이관
