from fastapi import HTTPException, APIRouter, status, Depends
from typing import Dict, Any, Optional

from services.auth_service import AuthService
from models.model import ResponseModel
from services.news_service import NewsService

router = APIRouter()
news_service = NewsService()

@router.get("/list", response_model=ResponseModel)
async def get_news(
    category: Optional[str] = None,
    limit: int = 20,
    offset: int = 0
):
    """뉴스 목록 조회"""
    result = await NewsService.get_articles(category, limit, offset)
    if not result["success"]:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=result["message"])
    return result

@router.get("/{article_id}", response_model=ResponseModel)
async def get_news_detail(article_id: str):
    """뉴스 상세 조회"""
    result = await NewsService.get_article_by_id(article_id)
    if not result["success"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["message"])
    return result

@router.get("/search", response_model=ResponseModel)
async def search_news(
    q: str,
    category: Optional[str] = None,
    limit: int = 20
):
    """뉴스 검색"""
    result = await NewsService.search_articles(q, category, limit)
    if not result["success"]:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=result["message"])
    return result

@router.post("/collect", response_model=ResponseModel)
async def collect_news():
    # current_user: Dict[str, Any] = Depends(AuthService.get_current_user)
    """뉴스 수집 (관리자만 가능)"""
    #if current_user.get("role") != "admin":
    #    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="권한이 없습니다.")

    #result = await NewsService.collect_news_from_rss()
    #if not result["success"]:
    #    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=result["message"])
    #return result
    return await news_service.collect_news_from_rss()