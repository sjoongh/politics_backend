"""refresh_issue_digest — 변경된 문서만 쓰고 기사 재조회가 없는지 가짜 DB로 검증."""
import services.issue_digest_service as mod
from tests.test_issue_service_detail import FakeDB, Snap, DocRef, Query


class WriteDB(FakeDB):
    def __init__(self, data):
        super().__init__(data)
        self.updates = []

    def collection(self, name):
        db = self

        class Q(Query):
            def document(self, _id):
                class R(DocRef):
                    def update(self, patch):
                        db.updates.append((self.id, patch))
                        db.data[self.coll][self.id].update(patch)

                    def set(self, doc):
                        db.updates.append((self.id, doc))
                        db.data.setdefault(self.coll, {})[self.id] = dict(doc)
                return R(db, self.coll, _id)
        return Q(self, name)


def _db():
    issues = {
        "n1": {"auto_generated": True, "newsworthiness": 8, "auto_key": "news:1", "active": True,
               "article_meta": {"a": {"leaning": "left", "at": "2026-11-09T00:00:00+00:00"}}},
        "b1": {"auto_generated": True, "newsworthiness": 5, "auto_key": "bill:1", "active": True, "article_meta": {}},
    }
    sources = {
        "v": {"id": "v", "type": "assembly_vote", "title": "표결: X", "published_at": "2026-11-08", "issue_ids": ["b1"],
              "link_status": "auto", "issue_id": "b1",
              "vote": {"yes": 10, "no": 2, "abstain": 0, "result": "가결", "party_breakdown": {"A": {"yes": 10, "no": 0, "abstain": 0}}}},
        "g": {"id": "g", "type": "gov_policy", "title": "기획재정부 발표", "published_at": "2026-11-10T01:00:00Z",
              "issue_id": "n1", "link_status": "auto", "position": "explain", "claim_summary": "설명"},
    }
    return WriteDB({"issues": issues, "source_items": sources, "articles": {}})


def test_refresh_writes_digest_for_changed_only(monkeypatch):
    db = _db()
    monkeypatch.setattr(mod, "db", db)
    out = mod.issue_digest_service.refresh(issue_ids=None)
    assert out["success"] and out["data"]["updated"] == 2 and db.get_all_calls == 0
    d_b1 = db.data["issues"]["b1"]["digest"]
    assert d_b1["has_vote"] and d_b1["vote"]["yes"] == 10 and d_b1["stance"][0]["basis"] == "vote"
    d_n1 = db.data["issues"]["n1"]["digest"]
    assert d_n1["has_gov"] and d_n1["stance"][0]["actor"] == "기획재정부" and d_n1["counts"]["media"] == 1
    # 두 번째 실행: 값이 같으면 쓰지 않는다(rank_at 제외 비교)
    n_before = len(db.updates)
    out2 = mod.issue_digest_service.refresh(issue_ids=None)
    assert out2["data"]["updated"] == 0 and len(db.updates) == n_before


def test_refresh_subset_and_active_default(monkeypatch):
    db = _db()
    db.data["issues"]["n1"].pop("active")
    monkeypatch.setattr(mod, "db", db)
    out = mod.issue_digest_service.refresh(issue_ids=["n1"])
    assert out["data"]["updated"] == 1 and db.data["issues"]["n1"]["active"] is True
    assert "digest" not in db.data["issues"]["b1"]


def test_ctx_reranks_unchanged_issues_and_quiets_old_news(monkeypatch):
    """변경 안 된 이슈도 순위 감쇠, 30일 무활동 뉴스 이슈는 소강(추가 읽기 없이 ctx 목록 사용)."""
    from services.pipeline_context import PipelineContext
    db = _db()
    stale = {"id": "s", "auto_generated": True, "newsworthiness": 20, "auto_key": "news:s", "active": True,
             "status": "진행중", "digest": {"counts": {}, "last_activity_at": "2026-10-01T00:00:00+00:00", "rank": 19.99}}
    fresh_unchanged = {"id": "f", "auto_generated": True, "newsworthiness": 5, "auto_key": "bill:f", "active": True,
                       "status": "가결", "digest": {"counts": {"vote": 1}, "last_activity_at": "2026-11-15T00:00:00+00:00",
                                                  "last_official_at": "2026-11-15", "rank": 30.0}}
    db.data["issues"].update({"s": dict(stale), "f": dict(fresh_unchanged)})
    monkeypatch.setattr(mod, "db", db)
    ctx = PipelineContext(lambda n: [], lambda: [dict(stale), dict(fresh_unchanged)], lambda d: [], lambda: set())
    out = mod.issue_digest_service.refresh(ctx=ctx)
    assert out["data"]["reranked"] == 2
    s_mem = next(i for i in ctx.active_issues() if i["id"] == "s")
    assert s_mem["status"] == "소강" and s_mem["digest"]["rank"] < 1   # 메모리에도 중첩 반영
    f_mem = next(i for i in ctx.active_issues() if i["id"] == "f")
    assert f_mem["status"] == "가결" and f_mem["digest"]["rank"] < 30.0  # 법안 이슈 상태는 건드리지 않음


def test_apply_dotted():
    d = {"digest": {"rank": 1, "counts": {}}}
    mod._apply_dotted(d, {"digest.rank": 2, "status": "소강"})
    assert d == {"digest": {"rank": 2, "counts": {}}, "status": "소강"}


class _NestedDB:
    """점 표기 update와 중첩 필드 범위 조회(>=, <)를 Firestore처럼 처리하는 최소 가짜."""
    def __init__(self, docs):
        self.docs = docs
        self.writes = []

    @staticmethod
    def _get(d, path):
        for k in path.split("."):
            d = (d or {}).get(k) if isinstance(d, dict) else None
        return d

    def collection(self, name):
        db = self

        class Ref:
            def __init__(self, _id):
                self.id = _id

            def update(self, patch):
                db.writes.append((self.id, patch))
                doc = db.docs[self.id]
                for k, v in patch.items():
                    cur = doc
                    *heads, last = k.split(".")
                    for h in heads:
                        cur = cur.setdefault(h, {})
                    cur[last] = v

        class Q:
            def __init__(self, filters=()):
                self.filters = filters

            def where(self, f, op, v):
                return Q(self.filters + ((f, op, v),))

            def document(self, _id):
                return Ref(_id)

            def stream(self):
                for _id, d in db.docs.items():
                    ok = True
                    for f, op, v in self.filters:
                        cur = _NestedDB._get(d, f)
                        if cur is None or (op == ">=" and not cur >= v) or (op == "<" and not cur < v):
                            ok = False
                    if ok:
                        yield Snap(_id, d)
        return Q()


def test_sweep_quiet_band_and_dotted_persist(monkeypatch):
    from datetime import datetime, timezone
    now = datetime(2026, 11, 16, tzinfo=timezone.utc)
    docs = {
        "crossed": {"auto_key": "news:a", "auto_generated": True, "newsworthiness": 20, "status": "진행중", "active": True,
                    "digest": {"counts": {}, "last_activity_at": "2026-10-16T12:00:00+00:00", "rank": 5.0}},   # 30.5일
        "old": {"auto_key": "news:b", "auto_generated": True, "newsworthiness": 20, "status": "진행중", "active": True,
                "digest": {"counts": {}, "last_activity_at": "2026-09-01T00:00:00+00:00", "rank": 5.0}},       # 구간 밖
        "recent": {"auto_key": "news:c", "auto_generated": True, "newsworthiness": 20, "status": "진행중", "active": True,
                   "digest": {"counts": {}, "last_activity_at": "2026-11-15T00:00:00+00:00", "rank": 5.0}},     # ctx 창 안
    }
    db = _NestedDB(docs)
    monkeypatch.setattr(mod, "db", db)
    n = mod.issue_digest_service._sweep_quiet(now)
    assert n == 1 and [w[0] for w in db.writes] == ["crossed"]
    assert docs["crossed"]["status"] == "소강"
    assert docs["crossed"]["digest"]["rank"] < 5.0 and "digest.rank" not in docs["crossed"]   # 중첩 필드로 저장
    assert docs["old"]["status"] == "진행중" and docs["recent"]["status"] == "진행중"
