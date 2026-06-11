import os
import requests
from utils.assembly_parse import extract_rows

BASE = "https://open.assembly.go.kr/portal/openapi/"


def _key():
    return os.getenv("ASSEMBLY_API_KEY", "")


def fetch_rows(service: str, params: dict = None, p_index: int = 1, p_size: int = 100) -> list:
    """서비스 호출 후 row 리스트 반환. 실패 시 []."""
    q = {"KEY": _key(), "Type": "json", "pIndex": p_index, "pSize": p_size}
    if params:
        q.update(params)
    try:
        r = requests.get(BASE + service, params=q, timeout=20)
        return extract_rows(r.json(), service)
    except Exception:
        return []


def fetch_all(service: str, params: dict = None, p_size: int = 100, max_pages: int = 20) -> list:
    """페이지네이션으로 전체 row 수집(상한 max_pages)."""
    out = []
    for i in range(1, max_pages + 1):
        rows = fetch_rows(service, params=params, p_index=i, p_size=p_size)
        if not rows:
            break
        out.extend(rows)
        if len(rows) < p_size:
            break
    return out
