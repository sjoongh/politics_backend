"""get_detail 일괄 조회 경로 — Firestore 가짜 객체로 서비스 계층 검증."""
import services.issue_service as mod


class Snap:
    def __init__(self, _id, data):
        self.id = _id
        self._d = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._d) if self._d is not None else None


class DocRef:
    def __init__(self, db, coll, _id):
        self.db, self.coll, self.id = db, coll, _id

    def get(self):
        return Snap(self.id, self.db.data.get(self.coll, {}).get(self.id))


class Query:
    def __init__(self, db, coll, filters=()):
        self.db, self.coll, self.filters = db, coll, filters

    def where(self, field, op, value):
        return Query(self.db, self.coll, self.filters + ((field, op, value),))

    def limit(self, n):
        return self

    def document(self, _id):
        return DocRef(self.db, self.coll, _id)

    def stream(self):
        for _id, d in self.db.data.get(self.coll, {}).items():
            ok = True
            for f, op, v in self.filters:
                cur = d.get(f)
                if op == "==" and cur != v:
                    ok = False
                if op == "array_contains" and v not in (cur or []):
                    ok = False
            if ok:
                yield Snap(_id, d)


class FakeDB:
    def __init__(self, data):
        self.data = data
        self.get_all_calls = 0

    def collection(self, name):
        return Query(self, name)

    def get_all(self, refs):
        self.get_all_calls += 1
        return [r.get() for r in refs]


def _fixture():
    ids = [f"a{i}" for i in range(1, 41)]
    meta = {i: {"source": "연합뉴스" if n % 2 else "한겨레", "leaning": "center" if n % 2 else "left",
                "at": f"2026-11-{(n % 28) + 1:02d}"} for n, i in enumerate(ids)}
    articles = {i: {"title": f"T{i}", "source": meta[i]["source"], "source_url": "u"} for i in ids if i != "a5"}
    issues = {"iss": {"title": "이슈", "article_ids": ids, "article_meta": meta, "events": []},
              "old": {"merged_into": "iss"}}
    sources = {
        "s1": {"id": "s1", "type": "gov_policy", "issue_id": "iss", "link_status": "auto", "title": "g"},
        "s2": {"id": "s2", "type": "assembly_vote", "issue_ids": ["iss"], "links": [], "link_status": "new", "title": "v"},
        "s3": {"id": "s3", "type": "assembly_bill", "issue_id": "iss", "link_status": "pending", "title": "b"},
    }
    return FakeDB({"issues": issues, "articles": articles, "source_items": sources})


def test_detail_batches_and_pages(monkeypatch):
    db = _fixture()
    monkeypatch.setattr(mod, "db", db)
    out = mod.issue_service.get_detail("iss")
    d = out["data"]
    assert db.get_all_calls == 1
    assert out["success"] and d["article_total"] == 40
    assert len(d["articles"]) <= 30 and d["articles_cursor"]
    # 최신순(메타 at 내림차순): 첫 기사는 at이 가장 큰 것
    assert d["articles"][0]["title"] == "Ta28"
    assert "media" not in d["source_panels"]
    assert [s["id"] for s in d["source_panels"]["government"]] == ["s1"]
    assert [s["id"] for s in d["source_panels"]["assembly_vote"]] == ["s2"]   # issue_ids 배열 경로
    assert d["source_panels"]["assembly_bill"] == []                           # pending 제외
    assert d["perspectives"]["breakdown"]["total"] == 40                       # article_meta 기준


def test_detail_follows_merge(monkeypatch):
    db = _fixture()
    monkeypatch.setattr(mod, "db", db)
    assert mod.issue_service.get_detail("old")["data"]["id"] == "iss"


def test_list_articles_second_page(monkeypatch):
    db = _fixture()
    monkeypatch.setattr(mod, "db", db)
    first = mod.issue_service.get_detail("iss")["data"]
    page = mod.issue_service.list_articles("iss", first["articles_cursor"])["data"]
    assert len(page["items"]) == 9          # 40 - 30 - 1 missing(a5 위치가 뒤쪽이면 달라질 수 있어 total로 검증)
    assert page["next_cursor"] is None
    assert db.get_all_calls == 2
