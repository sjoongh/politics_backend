import re
from typing import Optional

from fastapi import APIRouter, HTTPException, Response
from models.model import ResponseModel
from services.edition_service import edition_service
from utils.http_cache import cache_headers

router = APIRouter()
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@router.get("", response_model=ResponseModel)
def get_today(response: Response, date: Optional[str] = None):
    """날짜별 판. date 없으면 KST 오늘. 판이 없으면 edition=null(200)."""
    day = date or edition_service.today()
    if not _DATE.match(day):
        raise HTTPException(status_code=400, detail="date는 YYYY-MM-DD", headers=cache_headers(False))
    result = edition_service.get(day)
    response.headers.update(cache_headers(result.get("success", False)))
    return result
