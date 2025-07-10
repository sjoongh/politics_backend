# routers/statistics_router.py
from fastapi import APIRouter, status, HTTPException
from models.model import ResponseModel
from services.statistics_service import StatisticsService

router = APIRouter()

@router.get("/stats", response_model=ResponseModel)
async def get_statistics():
    """서비스 통계 조회"""
    try:
        stats = await StatisticsService.get_statistics_data()
        return {
            "success": True,
            "data": stats
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"통계 조회 중 오류가 발생했습니다: {str(e)}"
        )
