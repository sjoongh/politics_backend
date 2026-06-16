import os
from fastapi import APIRouter, HTTPException, status, Header, BackgroundTasks
from typing import Optional

from models.model import ResponseModel
from services.source_ingest_service import source_ingest_service
from services.source_link_service import source_link_service

router = APIRouter()


def _require_admin(x_admin_key: Optional[str]):
    expected = os.getenv("ADMIN_KEY")
    if not expected or x_admin_key != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="관리자 권한이 필요합니다.")


async def _run_pipeline():
    await source_ingest_service.ingest_gov_policy()
    await source_ingest_service.ingest_assembly_bills()
    await source_ingest_service.ingest_assembly_votes()
    await source_ingest_service.enrich_pending()
    await source_link_service.link_unlinked()


@router.post("/ingest", response_model=ResponseModel)
async def ingest(background_tasks: BackgroundTasks,
                 x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key")):
    """1차 소스 수집→보강→연결 파이프라인을 백그라운드로 실행(관리자)."""
    _require_admin(x_admin_key)
    background_tasks.add_task(_run_pipeline)
    return {"success": True, "message": "수집 파이프라인 시작", "data": {"status": "started"}}


@router.get("/pending", response_model=ResponseModel)
async def pending(limit: int = 50,
                  x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key")):
    """검수 대기(pending) 소스 목록(관리자)."""
    _require_admin(x_admin_key)
    return await source_link_service.list_pending(limit)


@router.post("/{source_id}/review", response_model=ResponseModel)
async def review(source_id: str, action: str, issue_id: Optional[str] = None,
                 x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key")):
    """검수 승인/거부(관리자). action=confirm|reject."""
    _require_admin(x_admin_key)
    result = await source_link_service.review(source_id, action, issue_id)
    if not result["success"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["message"])
    return result
