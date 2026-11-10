from fastapi.testclient import TestClient
import routers.today_router as tr
from main import app

client = TestClient(app)


def test_bad_date_400(monkeypatch):
    r = client.get("/api/today?date=2026-1-1")
    assert r.status_code == 400 and r.headers["cache-control"] == "no-store"


def test_missing_edition_is_200_null(monkeypatch):
    monkeypatch.setattr(tr.edition_service, "get", lambda d: {"success": True, "message": "", "data": {"edition": None, "other_issues": []}})
    r = client.get("/api/today?date=2026-01-01")
    assert r.status_code == 200 and r.json()["data"]["edition"] is None
    assert r.headers["cache-control"].startswith("public")
