from fastapi import FastAPI
from fastapi.testclient import TestClient
import routers.share_router as sr

app = FastAPI()
app.include_router(sr.router)
client = TestClient(app)

def test_issue_share_renders_og(monkeypatch):
    monkeypatch.setattr(sr, "_fetch_issue_meta",
                        lambda i: {"title": "추경 처리", "description": "국회 통과"})
    r = client.get("/share/issue/abc")
    assert r.status_code == 200
    assert 'og:title" content="추경 처리"' in r.text
    assert "/?issue=abc" in r.text
    assert "s-maxage" in r.headers.get("cache-control", "")

def test_missing_issue_returns_default_og_200(monkeypatch):
    monkeypatch.setattr(sr, "_fetch_issue_meta", lambda i: None)
    r = client.get("/share/issue/nope")
    assert r.status_code == 200
    assert "브리핑 코리아 · 정치 브리핑" in r.text

def test_article_share_renders_og(monkeypatch):
    monkeypatch.setattr(sr, "_fetch_article_meta",
                        lambda i: {"title": "기사 제목", "description": "기사 요약"})
    r = client.get("/share/article/xy")
    assert r.status_code == 200
    assert 'og:title" content="기사 제목"' in r.text
    assert "/?article=xy" in r.text


def test_issue_og_png_endpoint(monkeypatch):
    monkeypatch.setattr(sr, "_fetch_issue_meta",
                        lambda i: {"title": "추경 처리", "description": "국회 통과"})
    r = client.get("/share/issue/abc/og.png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert "s-maxage" in r.headers.get("cache-control", "")


def test_missing_article_og_png_returns_default_200(monkeypatch):
    monkeypatch.setattr(sr, "_fetch_article_meta", lambda i: None)
    r = client.get("/share/article/nope/og.png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"


def test_share_html_points_og_image_to_dynamic_png(monkeypatch):
    monkeypatch.setattr(sr, "_fetch_issue_meta",
                        lambda i: {"title": "추경 처리", "description": "국회 통과"})
    r = client.get("/share/issue/abc")
    assert 'og:image" content="' + sr.SHARE_BASE_URL + '/share/issue/abc/og.png' in r.text
    assert 'og:image:width" content="1200"' in r.text
    assert 'og:image:height" content="630"' in r.text


def test_og_png_render_failure_falls_back_to_default_image_redirect(monkeypatch):
    monkeypatch.setattr(sr, "_fetch_issue_meta", lambda i: {"title": "t", "description": "d"})
    def boom(**kw):
        raise RuntimeError("font missing")
    monkeypatch.setattr(sr, "render_og_image", boom)
    r = client.get("/share/issue/abc/og.png", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert r.headers["location"] == sr.OG_DEFAULT_IMAGE


def test_fetch_failure_is_not_cached(monkeypatch):
    monkeypatch.setattr(sr, "_fetch_issue_meta", lambda i: sr.FETCH_FAILED)
    r = client.get("/share/issue/abc")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    assert sr.OG_DEFAULT_IMAGE in r.text  # 장애 시엔 정적 기본 이미지
    p = client.get("/share/issue/abc/og.png")
    assert p.status_code == 200 and p.headers["cache-control"] == "no-store"


def test_invalid_id_rejected_without_fetch(monkeypatch):
    called = []
    monkeypatch.setattr(sr, "_fetch_issue_meta", lambda i: called.append(i))
    r = client.get("/share/issue/" + "x" * 81)
    assert r.status_code == 422
    assert called == []


def test_og_url_carries_content_version(monkeypatch):
    monkeypatch.setattr(sr, "_fetch_issue_meta",
                        lambda i: {"title": "t", "description": "d", "version": "deadbeef"})
    r = client.get("/share/issue/abc")
    assert "/share/issue/abc/og.png?v=deadbeef" in r.text


def test_og_png_rate_limit_redirects_to_default(monkeypatch):
    monkeypatch.setattr(sr, "_fetch_issue_meta", lambda i: None)
    monkeypatch.setattr(sr, "_og_limiter", sr.RateLimiter(max_calls=2, window_sec=60))
    assert client.get("/share/issue/a1/og.png").status_code == 200
    assert client.get("/share/issue/a2/og.png").status_code == 200
    r = client.get("/share/issue/a3/og.png", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == sr.OG_DEFAULT_IMAGE


def test_handlers_are_sync_so_blocking_work_runs_in_threadpool():
    import inspect
    for fn in (sr.share_issue, sr.share_article, sr.share_issue_og, sr.share_article_og):
        assert not inspect.iscoroutinefunction(fn)
