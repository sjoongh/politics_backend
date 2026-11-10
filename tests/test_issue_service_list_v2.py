"""list_summaries v2 — 정렬·필터·커서 경로를 Firestore 가짜로 검증."""
import services.issue_service as mod
from tests.test_issue_service_detail import FakeDB, Snap
from utils.cursor import encode_cursor


class OrderedQuery:
    """order_by/start_after/limit를 지원하는 가짜 쿼리(필터는 == 만)."""
    def __init__(self, db, coll, filters=(), orders=(), after=None, lim=None):
        self.db, self.coll, self.filters, self.orders, self.after, self.lim = db, coll, filters, orders, after, lim

    def where(self, f, op, v):
        return OrderedQuery(self.db, self.coll, self.filters + ((f, op, v),), self.orders, self.after, self.lim)

    def order_by(self, field, direction="ASCENDING"):
        return OrderedQuery(self.db, self.coll, self.filters, self.orders + ((field, direction),), self.after, self.lim)

    def start_after(self, values):
        return OrderedQuery(self.db, self.coll, self.filters, self.orders, values, self.lim)

    def limit(self, n):
        return OrderedQuery(self.db, self.coll, self.filters, self.orders, self.after, n)

    def document(self, _id):
        from tests.test_issue_service_detail import DocRef
        return DocRef(self.db, self.coll, _id)

    @staticmethod
    def _get(d, path):
        cur = d
        for p in path.split("."):
            cur = (cur or {}).get(p)
        return cur

    def stream(self):
        rows = []
        for _id, d in self.db.data.get(self.coll, {}).items():
            if all(self._get(d, f) == v for f, op, v in self.filters):
                rows.append((_id, d))
        for field, direction in reversed(self.orders):
            rows.sort(key=lambda r: (self._get(r[1], field) if field != "__name__" else r[0]) or 0,
                      reverse=(direction == "DESCENDING"))
        if self.after is not None:
            key_of = lambda r: [(self._get(r[1], f) if f != "__name__" else r[0]) for f, _ in self.orders]
            rows = [r for r in rows if self._cmp(key_of(r), list(self.after))]
        if self.lim:
            rows = rows[:self.lim]
        for _id, d in rows:
            yield Snap(_id, d)

    def _cmp(self, key, after):
        # 정렬: 첫 필드 DESC, 두 번째 __name__ ASC → 커서 뒤의 항목만
        if key[0] != after[0]:
            return key[0] < after[0]
        return key[1] > after[1]


class ListDB(FakeDB):
    def collection(self, name):
        return OrderedQuery(self, name)


def _db():
    issues = {}
    for i in range(1, 8):
        issues[f"i{i}"] = {"title": f"T{i}", "status": "진행중" if i % 2 else "가결", "active": True,
                           "digest": {"rank": float(i), "last_activity_at": f"2026-11-0{i}", "counts": {"media": 10 - i},
                                      "has_official": i > 4, "has_vote": i == 7, "has_gov": False}}
    issues["merged"] = {"title": "x", "active": False, "digest": {"rank": 99.0}}
    return ListDB({"issues": issues})


def test_v2_sorts_by_rank_desc_and_pages(monkeypatch):
    monkeypatch.setattr(mod, "db", _db())
    out = mod.issue_service.list_summaries(v=2, sort="rank", limit=3)["data"]
    assert [x["id"] for x in out["items"]] == ["i7", "i6", "i5"] and out["next_cursor"]
    nxt = mod.issue_service.list_summaries(v=2, sort="rank", limit=3, cursor=out["next_cursor"])["data"]
    assert [x["id"] for x in nxt["items"]] == ["i4", "i3", "i2"]
    last = mod.issue_service.list_summaries(v=2, sort="rank", limit=3, cursor=nxt["next_cursor"])["data"]
    assert [x["id"] for x in last["items"]] == ["i1"] and last["next_cursor"] is None


def test_v2_filter_and_digest_included(monkeypatch):
    monkeypatch.setattr(mod, "db", _db())
    out = mod.issue_service.list_summaries(v=2, filter="has_vote")["data"]
    assert [x["id"] for x in out["items"]] == ["i7"] and out["items"][0]["digest"]["counts"]["media"] == 3


def test_v2_status_filter_and_media_sort(monkeypatch):
    monkeypatch.setattr(mod, "db", _db())
    out = mod.issue_service.list_summaries(v=2, sort="media", filter="status:가결")["data"]
    assert [x["id"] for x in out["items"]] == ["i2", "i4", "i6"]


def test_v2_broken_cursor_is_first_page(monkeypatch):
    monkeypatch.setattr(mod, "db", _db())
    out = mod.issue_service.list_summaries(v=2, limit=2, cursor="!!garbage")["data"]
    assert [x["id"] for x in out["items"]] == ["i7", "i6"] and out["next_cursor"]


def test_v2_excludes_inactive(monkeypatch):
    monkeypatch.setattr(mod, "db", _db())
    ids = [x["id"] for x in mod.issue_service.list_summaries(v=2, limit=50)["data"]["items"]]
    assert "merged" not in ids
