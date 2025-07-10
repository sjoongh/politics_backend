from fastapi import APIRouter, status, Depends, HTTPException
from models.model import UserUpdate, UserCreate, UserLogin, ResponseModel
from services.auth_service import auth_service
from typing import Dict, Any

router = APIRouter()

@router.post("/register", response_model=ResponseModel, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate):
    """사용자 회원가입"""
    result = await auth_service.register_user(user_data)
    if result["success"]:
        return result
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["message"])


@router.post("/login", response_model=ResponseModel)
async def login(login_data: UserLogin):
    """사용자 로그인"""
    result = await auth_service.login_user(login_data)
    if result["success"]:
        return result
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=result["message"])


@router.get("/me", response_model=ResponseModel)
async def get_current_user_info(current_user: Dict[str, Any] = Depends(auth_service.get_current_user)):
    """현재 사용자 정보 조회"""
    return {
        "success": True,
        "message": "사용자 정보 조회 성공",
        "data": {
            "user": {
                "uid": current_user["uid"],
                "email": current_user["email"],
                "name": current_user["name"],
                "role": current_user["role"],
                "interests": current_user.get("interests", []),
                "notification_enabled": current_user.get("notification_enabled", True),
                "avatar_url": current_user.get("avatar_url")
            }
        }
    }


@router.put("/profile", response_model=ResponseModel)
async def update_profile(
    update_data: UserUpdate, 
    current_user: Dict[str, Any] = Depends(auth_service.get_current_user)
):
    """사용자 프로필 업데이트"""
    result = await auth_service.update_user_profile(
        current_user["uid"], 
        update_data.dict(exclude_unset=True)
    )
    if result["success"]:
        return result
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["message"])
