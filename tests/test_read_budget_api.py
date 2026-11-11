"""API 읽기 예산: 공개 GET 캐시 헤더, 최근 기사 후보 공유 로더, 검색 전체 스캔 제거, 중복판정 fail-closed."""
import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException

import services.news_service as ns
from common.exception_handlers import http_exception_handler
from utils.http_cache import cache_headers, private_headers


# ---------- 가짜 Firestore ----------
class _Doc:
    def __init__(self, data, exists=True):
        self._d, self.exists, self.id = data, exists, (data or {}).get("id", "x")

    def to_dict(self):
        return dict(self._d) if self._d is not None else None


class _Query:
    def __init__(self, db, name):
        self.db, self.name, self.ops = db, name, []

    def where(self, *a, **k):
        self.ops.append(("where", a)); return self

    def order_by(self, *a, **k):
        self.ops.append(("order_by", a)); return self

    def limit(self, n):
        self.ops.append(("limit", n)); return self

    def offset(self, n):
        self.ops.append(("offset", n)); return self

    def stream(self):
        self.db.streams.append((self.name, list(self.ops)))
        n = next((v for op, v in self.ops if op == "limit"), None)
        rows = self.db.rows.get(self.name, [])
        return [_Doc(r) for r in (rows if n is None else rows[:n])]

    def document(self, doc_id):
        return _Ref(self.db, self.name, doc_id)


class _Ref:
    def __init__(self, db, name, doc_id):
        self.db, self.name, self.doc_id = db, name, doc_id

    def get(self):
        if self.db.raise_on_get:
            raise RuntimeError("429 Quota exceeded.")
        hit = [r for r in self.db.rows.get(self.name, []) if r.get("id") == self.doc_id]
        return _Doc(hit[0] if hit else None, exists=bool(hit))


class FakeDB:
    def __init__(self, rows=None, raise_on_get=False):
        self.rows, self.streams, self.raise_on_get = rows or {}, [], raise_on_get

    def collection(self, name):
        return _Query(self, name)


def _articles(n):
    return [{"id": f"a{i}", "title": f"기사 {i} 예산", "ai_summary": "요약", "category": "정치" if i % 2 else "정부",
             "published_at": f"2026-11-{30 - i % 30:02d} 00:00:00", "source": "연합뉴스", "keywords": ["예산"]}
            for i in range(n)]


@pytest.fixture
def fake(monkeypatch):
    db = FakeDB({"articles": _articles(400)})
    monkeypatch.setattr(ns, "db", db)
    ns.reset_recent_cache()
    return db


# ---------- 캐시 헤더 ----------
def test_public_cache_serves_stale_on_origin_error():
    v = cache_headers(True)["Cache-Control"]
    assert "public" in v and "s-maxage=300" in v and "stale-if-error=86400" in v


def test_private_headers_never_cached():
    assert private_headers() == {"Cache-Control": "private, no-store"}


# ---------- 최근 기사 후보 공유 로더 ----------
def test_recent_pool_is_bounded_and_shared(fake):
    run = asyncio.run
    run(ns.news_service.search_articles("예산"))
    run(ns.news_service.search_articles("기사 3", category="정치"))
    run(ns.news_service.get_digest(["예산"]))
    assert len(fake.streams) == 1                      # 세 호출이 한 번만 읽는다
    name, ops = fake.streams[0]
    assert name == "articles" and ("limit", ns.RECENT_POOL) in ops


def test_search_never_scans_whole_collection(fake):
    res = asyncio.run(ns.news_service.search_articles("기사", limit=5))
    assert res["success"] and res["data"]["count"] == 5
    assert all(any(op == "limit" for op, _ in ops) for _, ops in fake.streams)


def test_search_category_filter_applied_in_memory(fake):
    res = asyncio.run(ns.news_service.search_articles("기사", category="정부", limit=50))
    assert res["data"]["articles"] and all(a["category"] == "정부" for a in res["data"]["articles"])


def test_cached_candidates_are_copies(fake):
    first = ns.recent_articles()
    first[0]["reason"] = "user-specific"
    assert "reason" not in ns.recent_articles()[0]     # 한 사용자의 사유가 다른 응답에 새지 않음


def test_news_list_first_pages_come_from_pool(fake):
    res = asyncio.run(ns.news_service.get_articles(None, limit=20, offset=40))
    assert [a["id"] for a in res["data"]["articles"]] == [f"a{i}" for i in range(40, 60)]
    assert not any(op == "offset" for _, ops in fake.streams for op, _ in ops)   # offset 과금 없음


def test_news_list_beyond_pool_falls_back_to_query(fake):
    asyncio.run(ns.news_service.get_articles(None, limit=20, offset=ns.RECENT_POOL))
    assert any(op == "offset" for _, ops in fake.streams for op, _ in ops)


# ---------- 중복판정 fail-closed ----------
def test_doc_exists_fails_closed_on_read_error(monkeypatch):
    monkeypatch.setattr(ns, "db", FakeDB(raise_on_get=True))
    svc = ns.NewsService()
    assert asyncio.run(svc._doc_exists("articles", "a1")) is True   # 읽기 실패 = 처리 안 함
    assert svc.read_errors == 1


def test_doc_exists_reports_missing_when_readable(monkeypatch):
    monkeypatch.setattr(ns, "db", FakeDB({"articles": [{"id": "a1"}]}))
    svc = ns.NewsService()
    assert asyncio.run(svc._doc_exists("articles", "a1")) is True
    assert asyncio.run(svc._doc_exists("articles", "zz")) is False
    assert svc.read_errors == 0


# ---------- 라우터 헤더 ----------
def _client(router_module, prefix):
    app = FastAPI()
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.include_router(router_module.router, prefix=prefix)
    return app, TestClient(app)


def _ok(data=None):
    async def f(*a, **k):
        return {"success": True, "message": "", "data": data or {}}
    return f


def _fail(*a, **k):
    async def f(*a, **k):
        return {"success": False, "message": "429 Quota exceeded."}
    return f()


def test_news_public_gets_are_cdn_cacheable(monkeypatch):
    import routers.news_router as nr
    for name in ("get_articles", "search_articles", "ai_search", "get_digest", "get_article_by_id"):
        monkeypatch.setattr(nr.news_service, name, _ok())
    _, c = _client(nr, "/api/news")
    for url in ("/api/news/list", "/api/news/search?q=a", "/api/news/search/ai?q=a",
                "/api/news/digest?interests=a", "/api/news/art1"):
        r = c.get(url)
        assert r.status_code == 200, url
        assert r.headers["cache-control"].startswith("public"), url


def test_news_errors_are_not_cached(monkeypatch):
    import routers.news_router as nr
    monkeypatch.setattr(nr.news_service, "get_articles", lambda *a, **k: _fail())
    _, c = _client(nr, "/api/news")
    r = c.get("/api/news/list")
    assert r.status_code == 500 and r.headers["cache-control"] == "no-store"


def test_foryou_is_private(monkeypatch):
    import routers.news_router as nr
    monkeypatch.setattr(nr.news_service, "personalized_feed", _ok({"items": []}))
    app, c = _client(nr, "/api/news")
    app.dependency_overrides[nr.auth_service.get_current_user] = lambda: {"email": "u@x", "interests": []}
    r = c.get("/api/news/foryou")
    assert r.status_code == 200 and r.headers["cache-control"] == "private, no-store"


def test_politics_and_summary_gets_are_cacheable(monkeypatch):
    import routers.politics_router as pr
    import routers.summary_router as sr

    async def _list(*a, **k):
        return []
    for name in ("get_president_info", "get_recent_policies", "get_political_statements"):
        monkeypatch.setattr(pr.politics_service, name, _list)
    _, c = _client(pr, "/api/politics")
    for url in ("/api/politics/president", "/api/politics/policies", "/api/politics/statements"):
        assert c.get(url).headers["cache-control"].startswith("public"), url

    monkeypatch.setattr(sr.ai_summary_service, "get_daily_summary", _ok({"summary": None}))
    _, c2 = _client(sr, "/api/summaries")
    assert c2.get("/api/summaries/daily").headers["cache-control"].startswith("public")


def test_collect_stops_on_read_errors_without_ai_calls(monkeypatch):
    """쿼터 429로 중복판정이 실패하면 본문 크롤·AI 요약 없이 그 실행을 멈춘다."""
    import types
    monkeypatch.setattr(ns, "db", FakeDB(raise_on_get=True))
    entries = [{"title": f"t{i}", "summary": "s", "link": f"https://x/{i}"} for i in range(10)]
    fake_feed = types.SimpleNamespace(bozo=False, entries=entries, feed={"title": "연합뉴스"})
    monkeypatch.setattr(ns, "feedparser", types.SimpleNamespace(parse=lambda text: fake_feed))
    fetched = []
    monkeypatch.setattr(ns.requests, "get", lambda url, **k: fetched.append(url) or types.SimpleNamespace(text="", encoding=None))
    calls = []

    async def _summ(*a, **k):
        calls.append(a)
        return {"success": False, "message": "x"}
    monkeypatch.setattr(ns.ai_summary_service, "summarize_by_category", _summ)
    monkeypatch.setattr(ns, "fetch_article_text", lambda url: calls.append(url) or "")
    svc = ns.NewsService()
    svc.request_delay = 0
    res = asyncio.run(svc.collect_news_from_rss())
    assert res["success"] and calls == []
    assert svc.read_errors == ns.READ_ERROR_BREAKER   # 첫 피드 안에서도 곧바로 멈춤
    assert len(fetched) == 1          # 첫 피드에서 멈추고 나머지 피드는 요청하지 않음
