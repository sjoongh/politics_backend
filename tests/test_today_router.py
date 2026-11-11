from fastapi.testclient import TestClient
import routers.today_router as tr
from fastapi import FastAPI
from starlette.exceptions import HTTPException as StarletteHTTPException
from common.exception_handlers import http_exception_handler
import routers.today_router as _r

# main은 import 시 다른 라우터가 Firebase를 초기화하므로, 대상 라우터만 담은 앱으로 테스트한다(CI 자격 증명 없음)
app = FastAPI()
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.include_router(_r.router, prefix="/api/today")
client = TestClient(app)


def test_bad_date_400(monkeypatch):
    r = client.get("/api/today?date=2026-1-1")
    assert r.status_code == 400 and r.headers["cache-control"] == "no-store"


def test_missing_edition_is_200_null(monkeypatch):
    monkeypatch.setattr(tr.edition_service, "get", lambda d: {"success": True, "message": "", "data": {"edition": None, "other_issues": []}})
    r = client.get("/api/today?date=2026-01-01")
    assert r.status_code == 200 and r.json()["data"]["edition"] is None
    assert r.headers["cache-control"].startswith("public")
