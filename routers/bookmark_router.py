from fastapi import APIRouter, status, Depends, HTTPException
from models.model import BookmarkBase, ResponseModel
from typing import Dict, Any
from services.bookmark_service import bookmark_service
from services.auth_service import auth_service

router = APIRouter()

@router.post("", response_model=ResponseModel)
async def add_bookmark(
    bookmark_data: BookmarkBase,
    current_user: Dict[str, Any] = Depends(auth_service.get_current_user)
):
    """기사 북마크 추가"""
    bookmark = bookmark_service.add_bookmark(current_user["uid"], bookmark_data)

    if not bookmark:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="북마크 추가 중 오류가 발생했습니다."
        )

    return {
        "success": True,
        "message": "북마크가 추가되었습니다.",
        "data": {"bookmark": bookmark}
    }


@router.get("/list", response_model=ResponseModel)
async def get_bookmarks(
    limit: int = 20,
    current_user: Dict[str, Any] = Depends(auth_service.get_current_user)
):
    """사용자 북마크 목록 조회"""
    bookmarks = bookmark_service.get_bookmarks(current_user["uid"], limit)

    if bookmarks is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="북마크 조회 중 오류가 발생했습니다."
        )

    return {
        "success": True,
        "data": {"bookmarks": bookmarks, "count": len(bookmarks)}
    }
