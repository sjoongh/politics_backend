from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from services.auth_service import auth_service
from models.model import ResponseModel
from services.ai_service import ai_summary_service

router = APIRouter()


@router.get("/daily", response_model=ResponseModel)
async def get_daily_summary(date: Optional[str] = None):
    """일일 뉴스 요약 조회"""
    result = await ai_summary_service.get_daily_summary(date)

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("message", "일일 요약 조회 실패")
        )

    return result


@router.post("/daily", response_model=ResponseModel)
async def create_daily_summary(
    date: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(auth_service.get_current_user)
):
    """일일 뉴스 요약 생성 (관리자만 가능)"""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="권한이 없습니다."
        )

    result = await ai_summary_service.generate_daily_summary(date)

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("message", "요약 생성 실패")
        )

    return result