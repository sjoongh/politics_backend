import os
from fastapi import HTTPException, APIRouter, status, Depends, BackgroundTasks, Header, Query
from typing import Dict, Any, Optional

from services.auth_service import auth_service
from models.model import ResponseModel
from services.news_service import news_service

router = APIRouter()


def _require_admin(x_admin_key: Optional[str]):
    expected = os.getenv("ADMIN_KEY")
    if not expected or x_admin_key != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="관리자 권한이 필요합니다.")

@router.get("/list", response_model=ResponseModel)
async def get_news(
    category: Optional[str] = None,
    limit: int = 20,
    offset: int = 0
):
    """뉴스 목록 조회"""
    result = await news_service.get_articles(category, limit, offset)
    if not result["success"]:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=result["message"])
    return result

@router.get("/search", response_model=ResponseModel)
async def search_news(
    q: str,
    category: Optional[str] = None,
    limit: int = 20
):
    """뉴스 검색"""
    result = await news_service.search_articles(q, category, limit)
    if not result["success"]:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=result["message"])
    return result

@router.get("/search/ai", response_model=ResponseModel)
async def ai_search_news(
    q: str = Query(..., min_length=1, max_length=200),
    include_briefing: bool = False,
    limit: int = Query(20, ge=1, le=50),
):
    """AI 자연어 검색. Gemini로 질의를 구조화해 랭킹하고, 옵션으로 짧은 브리핑을 생성.
    Gemini 키가 없거나 실패하면 부분문자열 폴백으로 동작한다."""
    query = q.strip()
    if not query:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="검색어를 입력해 주세요.")
    result = await news_service.ai_search(query, include_briefing=include_briefing, limit=limit)
    if not result["success"]:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=result["message"])
    return result

@router.post("/collect", response_model=ResponseModel)
async def collect_news(
    background_tasks: BackgroundTasks,
    x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key"),
):
    """뉴스 수집을 백그라운드로 시작(비차단). 관리자 키 필요."""
    _require_admin(x_admin_key)
    background_tasks.add_task(news_service.collect_news_from_rss)
    return {"success": True, "message": "뉴스 수집을 시작했습니다.", "data": {"status": "started"}}

@router.get("/digest", response_model=ResponseModel)
async def get_digest(interests: str = "", limit: int = 30):
    """관심 키워드(쉼표구분)로 맞춤 기사 조회."""
    items = [i for i in interests.split(",") if i.strip()]
    return await news_service.get_digest(items, limit)

@router.get("/foryou", response_model=ResponseModel)
async def get_for_you(
    limit: int = Query(30, ge=1, le=50),
    current_user: Dict[str, Any] = Depends(auth_service.get_current_user),
):
    """개인 맞춤 'For You' 피드(로그인 필요). 관심사 + 북마크 기반 순수 랭킹 + 다양성.
    관심사·북마크가 없으면 '시작 추천' 모드."""
    # 사용자 식별자: uid 없을 수 있어 email 폴백(KeyError 방지 — codex)
    uid = current_user.get("uid") or current_user.get("email")
    result = await news_service.personalized_feed(
        uid, current_user.get("interests", []), limit=limit)
    if not result["success"]:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=result["message"])
    return result

@router.get("/{article_id}", response_model=ResponseModel)
async def get_news_detail(article_id: str):
    """뉴스 상세 조회"""
    result = await news_service.get_article_by_id(article_id)
    if not result["success"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["message"])
    return result