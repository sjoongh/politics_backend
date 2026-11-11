import os
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Response
from utils.http_cache import cache_headers
from models.model import MemberCreate, ResponseModel
from services.member_service import member_service
from utils.member_rules import has_missing_source

router = APIRouter()


def _require_admin(x_admin_key: Optional[str]):
    expected = os.getenv("ADMIN_KEY")
    if not expected or x_admin_key != expected:
        raise HTTPException(status_code=401, detail="관리자 권한이 필요합니다.")


@router.get("", response_model=ResponseModel)
async def list_members(response: Response, party: Optional[str] = None, limit: int = 20, offset: int = 0):
    # 앱이 limit=400(전체)으로 부르므로 호출마다 최대 400건 읽기 → CDN 캐시 필수
    result = await member_service.list_members(party=party, limit=limit, offset=offset)
    response.headers.update(cache_headers(result.get("success", False)))
    return result


@router.get("/{member_id}", response_model=ResponseModel)
def get_member(member_id: str, response: Response):
    result = member_service.get_member(member_id)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("message", "의원을 찾을 수 없습니다."),
                            headers=cache_headers(False))
    response.headers.update(cache_headers(True))
    return result


@router.post("", response_model=ResponseModel)
async def create_member(member: MemberCreate, x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key")):
    _require_admin(x_admin_key)
    records = [r.dict() for r in member.criminal_records]
    if has_missing_source(records):
        raise HTTPException(status_code=400, detail="모든 전과 항목에 출처(source_url)가 필요합니다.")
    return await member_service.upsert_member(member)
