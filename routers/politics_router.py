from fastapi import APIRouter, status
from models.model import ResponseModel
from typing import List
from services.politics_service import politics_service
from models.model import ParliamentaryActivity
from models.model import PoliticalStatement

router = APIRouter()

@router.get("/president", response_model=ResponseModel)
async def get_president():
    """대통령 정보 반환"""
    data = await politics_service.get_president_info()
    return {
        "success": True,
        "message": "대통령 정보 조회 성공",
        "data": {"president": data}
    }

@router.get("/policies", response_model=ResponseModel)
async def get_policies():
    """최근 정책 반환"""
    data = await politics_service.get_recent_policies()
    return {
        "success": True,
        "message": "정책 정보 조회 성공",
        "data": {"policies": data}
    }

# @router.get("/parliament", response_model=ResponseModel)
# async def get_parliament():
#     """국회 활동 반환"""
#     data = await politics_service.get_parliamentary_activities()
#     return {
#         "success": True,
#         "message": "국회 활동 조회 성공",
#         "data": {"activities": data}
#     }

@router.get("/statements", response_model=ResponseModel)
async def get_statements():
    """정치인 발언 반환"""
    data = await politics_service.get_political_statements()
    return {
        "success": True,
        "message": "정치인 발언 조회 성공",
        "data": {"statements": data}
    }

@router.post("/policy")
async def create_policies(activities: List[ParliamentaryActivity]):
    results = []
    for activity in activities:
        result = await politics_service.save_parliamentary_activity(activity)
        results.append(result)
    return results

@router.post("/statements")
async def create_statements(statements: List[PoliticalStatement]):
    results = []
    for statement in statements:
        result = await politics_service.save_political_statement(statement)
        results.append(result)
    return results
