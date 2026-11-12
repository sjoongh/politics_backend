"""미처리 예외로 생긴 500에도 CORS 헤더가 붙어야 웹 앱이 오류 응답을 읽을 수 있다."""
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from common.exception_handlers import configure_errors_and_cors

ORIGIN = {"Origin": "https://koreanpolitical.web.app"}


def _client():
    app = FastAPI()
    configure_errors_and_cors(app)

    @app.get("/boom")
    async def boom():
        raise RuntimeError("boom")

    @app.get("/gone")
    async def gone():
        raise HTTPException(status_code=404, detail="없음")

    return TestClient(app, raise_server_exceptions=False)


def test_unhandled_error_keeps_cors_header():
    r = _client().get("/boom", headers=ORIGIN)
    assert r.status_code == 500
    assert r.headers.get("access-control-allow-origin") == "*"
    assert r.headers.get("cache-control") == "no-store"
    assert r.json()["success"] is False


def test_http_error_keeps_cors_header():
    r = _client().get("/gone", headers=ORIGIN)
    assert r.status_code == 404
    assert r.headers.get("access-control-allow-origin") == "*"
    assert r.json()["message"] == "없음"


def test_main_uses_shared_configuration():
    src = open("main.py", encoding="utf-8").read()
    assert "configure_errors_and_cors(app)" in src and "CORSMiddleware" not in src
