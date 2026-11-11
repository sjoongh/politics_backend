from fastapi.testclient import TestClient
import routers.source_router as sr
from fastapi import FastAPI
from starlette.exceptions import HTTPException as StarletteHTTPException
from common.exception_handlers import http_exception_handler
import routers.source_router as _r

# main은 import 시 다른 라우터가 Firebase를 초기화하므로, 대상 라우터만 담은 앱으로 테스트한다(CI 자격 증명 없음)
app = FastAPI()
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.include_router(_r.router, prefix="/api/sources")
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
