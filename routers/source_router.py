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
    # 실행 락: 최근 10분 내 실행됐으면 skip(반복 호출 비용 폭주 방지 — codex)
    from datetime import datetime, timezone, timedelta
    from firebase.firebase_config import db
    lock = db.collection("_meta").document("ingest_lock")
    snap = lock.get()
    if snap.exists:
        last = snap.to_dict().get("at")
        try:
            if last and datetime.fromisoformat(last) > datetime.now(timezone.utc) - timedelta(minutes=10):
                print("[ingest] skipped (locked)")
                return
        except ValueError:
            pass
    lock.set({"at": datetime.now(timezone.utc).isoformat()})
    print(await source_ingest_service.ingest_gov_policy())
    print(await source_ingest_service.ingest_assembly_bills())
    print(await source_ingest_service.ingest_assembly_votes())
    print(await source_ingest_service.enrich_pending())
    from services.issue_cluster_service import issue_cluster_service
    print(await issue_cluster_service.generate_bill_issues())  # 법안 기준 이슈 자동생성(링크 전)
    print(await source_link_service.link_unlinked())
    print(await source_link_service.crosslink())               # gov/news 교차연결(4단 패널 채움)
    from services.news_issue_service import news_issue_service
    print(await news_issue_service.generate_news_issues())      # 뉴스 기반 현안 이슈 생성
    print(await news_issue_service.summarize_pending_issues())  # 자동 이슈 AI 사건요약


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
