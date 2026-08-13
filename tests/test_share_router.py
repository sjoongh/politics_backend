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
