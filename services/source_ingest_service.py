"""1차 소스 수집(정부/국회) → source_items 컬렉션 정규화 저장.

저작권 안전: 원문 전문 저장 안 함. 제목 + (AI)요약 + 원문 링크 + 출처표기만.
AI 보강은 Task 5에서 수집 후 배치로 채운다.
"""
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
import httpx

from firebase.firebase_config import db
from utils.source_item import normalize_gov_policy, normalize_bill

KOREA_RSS = "https://www.korea.kr/rss/policy.xml"


def _parse_rss(xml_bytes):
    root = ET.fromstring(xml_bytes)
    out = []
    for it in root.findall(".//item"):
        d = {}
        for ch in it:
            d[ch.tag.split("}")[-1]] = (ch.text or "")
        out.append(d)
    return out


def _now():
    return datetime.now(timezone.utc).isoformat()


def _save_new(source):
    """중복(이미 존재) 아니면 저장. 신규 1, 기존 0 반환."""
    ref = db.collection("source_items").document(source["id"])
    if ref.get().exists:
        return 0
    source["created_at"] = _now()
    source["updated_at"] = source["created_at"]
    ref.set(source)
    return 1


class SourceIngestService:
    async def ingest_gov_policy(self, limit: int = 50) -> dict:
        """정책브리핑 korea.kr RSS 수집."""
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.get(KOREA_RSS)
            items = _parse_rss(r.content)[:limit]
            new = sum(_save_new(normalize_gov_policy(it)) for it in items)
            return {"success": True, "message": "정부 소스 수집",
                    "data": {"new": new, "total": len(items)}}
        except Exception as e:
            print(f"[ingest_gov_policy] {e!r}")
            return {"success": False, "message": "정부 소스 수집 실패"}

    async def ingest_assembly_bills(self, bills) -> dict:
        """열린국회 법안 리스트(dict) → assembly_bill 정규화 저장.
        호출부에서 assembly_client로 조회한 원자료를 넘긴다."""
        try:
            new = sum(_save_new(normalize_bill(b)) for b in (bills or []))
            return {"success": True, "message": "법안 수집", "data": {"new": new, "total": len(bills or [])}}
        except Exception as e:
            print(f"[ingest_assembly_bills] {e!r}")
            return {"success": False, "message": "법안 수집 실패"}


source_ingest_service = SourceIngestService()
