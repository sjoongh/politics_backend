import os
from typing import Optional
from fastapi import APIRouter, Header, HTTPException
from models.model import ResponseModel
from services.assembly_service import assembly_service

router = APIRouter()


def _require_admin(x_admin_key: Optional[str]):
    expected = os.getenv("ADMIN_KEY")
    if not expected or x_admin_key != expected:
        raise HTTPException(status_code=401, detail="관리자 권한이 필요합니다.")


@router.post("/sync/members", response_model=ResponseModel)
async def sync_members(x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key")):
    _require_admin(x_admin_key)
    return await assembly_service.sync_members()


@router.post("/sync/bills", response_model=ResponseModel)
async def sync_bills(x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key")):
    _require_admin(x_admin_key)
    return await assembly_service.sync_bills()


@router.post("/sync/votes", response_model=ResponseModel)
async def sync_votes(x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key")):
    _require_admin(x_admin_key)
    return await assembly_service.sync_votes()
