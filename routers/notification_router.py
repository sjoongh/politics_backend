from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, status, HTTPException
from services.auth_service import AuthService
from models.model import ResponseModel
from services.notification_service import notification_service

router = APIRouter()


@router.get("/user", response_model=ResponseModel)
async def get_notifications(
    is_read: Optional[bool] = None,
    limit: int = 20,
    current_user: Dict[str, Any] = Depends(AuthService.get_current_user)
):
    """사용자 알림 목록 조회"""
    result = await notification_service.get_user_notifications(
        current_user["uid"], is_read, limit
    )

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result["message"]
        )

    return result


@router.put("/user/{notification_id}/read", response_model=ResponseModel)
async def mark_notification_read(
    notification_id: str,
    current_user: Dict[str, Any] = Depends(AuthService.get_current_user)
):
    """알림을 읽음으로 표시"""
    result = await notification_service.mark_notification_as_read(
        notification_id, current_user["uid"]
    )

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["message"]
        )

    return result


@router.put("/user/read-all", response_model=ResponseModel)
async def mark_all_notifications_read(
    current_user: Dict[str, Any] = Depends(AuthService.get_current_user)
):
    """모든 알림을 읽음으로 표시"""
    result = await notification_service.mark_all_notifications_as_read(current_user["uid"])

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result["message"]
        )

    return result
