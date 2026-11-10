from fastapi.testclient import TestClient
import routers.source_router as sr
from main import app

client = TestClient(app)


def test_type_required_400():
    r = client.get("/api/sources")
    assert r.status_code == 400 and r.headers["cache-control"] == "no-store"


def test_bad_type_400():
    assert client.get("/api/sources?type=zzz").status_code == 400


def test_ok_shape(monkeypatch):
    monkeypatch.setattr(sr.source_list_service, "list",
                        lambda type_, cursor, limit: {"success": True, "message": "", "data": {"items": [{"id": "v", "type": type_}], "next_cursor": "abc"}})
    r = client.get("/api/sources?type=assembly_vote&limit=5")
    body = r.json()
    assert r.status_code == 200 and body["data"]["items"][0]["type"] == "assembly_vote" and body["data"]["next_cursor"] == "abc"
    assert r.headers["cache-control"].startswith("public")
