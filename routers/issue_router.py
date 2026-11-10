import os
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Response
from utils.http_cache import cache_headers
from models.model import IssueSeed, EventSeed, ResponseModel
from services.issue_service import issue_service

router = APIRouter()


def _require_admin(x_admin_key: Optional[str]):
    expected = os.getenv("ADMIN_KEY")
    if not expected or x_admin_key != expected:
        raise HTTPException(status_code=401, detail="관리자 권한이 필요합니다.")


@router.get("", response_model=ResponseModel)
async def list_issues(status: Optional[str] = None, category: Optional[str] = None, limit: int = 20, offset: int = 0):
    return await issue_service.list_summaries(status=status, category=category, limit=limit, offset=offset)


@router.get("/{issue_id}", response_model=ResponseModel)
def get_issue(issue_id: str, response: Response):
    # 동기 Firestore 호출 → def 핸들러(스레드풀)로 이벤트 루프를 막지 않는다
    result = issue_service.get_detail(issue_id)
    if not result.get("success"):
        response.headers.update(cache_headers(False))
        raise HTTPException(status_code=404, detail=result.get("message", "이슈를 찾을 수 없습니다."))
    response.headers.update(cache_headers(True))
    return result


@router.get("/{issue_id}/articles", response_model=ResponseModel)
def list_issue_articles(issue_id: str, response: Response, cursor: Optional[str] = None, limit: int = 30):
    result = issue_service.list_articles(issue_id, cursor=cursor, limit=max(1, min(limit, 100)))
    response.headers.update(cache_headers(result.get("success", False)))
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("message", "이슈를 찾을 수 없습니다."))
    return result


@router.post("", response_model=ResponseModel)
async def create_issue(seed: IssueSeed, x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key")):
    _require_admin(x_admin_key)
    result = await issue_service.create(seed)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message"))
    return result


@router.patch("/{issue_id}", response_model=ResponseModel)
async def update_issue(issue_id: str, fields: dict, x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key")):
    _require_admin(x_admin_key)
    result = await issue_service.update(issue_id, fields)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message"))
    return result


@router.post("/{issue_id}/events", response_model=ResponseModel)
async def add_event(issue_id: str, event: EventSeed, x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key")):
    _require_admin(x_admin_key)
    result = await issue_service.add_event(issue_id, event)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("message"))
    return result


@router.post("/{issue_id}/articles", response_model=ResponseModel)
async def add_articles(issue_id: str, body: dict, x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key")):
    _require_admin(x_admin_key)
    result = await issue_service.add_articles(issue_id, body.get("article_ids", []))
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("message"))
    return result
