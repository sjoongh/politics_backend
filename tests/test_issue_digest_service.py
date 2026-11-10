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
