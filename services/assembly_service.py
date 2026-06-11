import os
from datetime import datetime

from firebase.firebase_config import db
from services.assembly_client import fetch_all, fetch_rows

AGE = os.getenv("ASSEMBLY_AGE", "22")
MEMBERS = "members"


def _now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


class AssemblyService:
    @staticmethod
    async def sync_members() -> dict:
        rows = fetch_all("nwvrqwxyaytdsfvhu", p_size=300, max_pages=3)
        if not rows:
            return {"success": False, "message": "의원 명단을 가져오지 못했습니다."}
        count = 0
        for m in rows:
            mona = m.get("MONA_CD")
            if not mona:
                continue
            doc = {
                "id": mona,
                "assembly_id": mona,
                "name": m.get("HG_NM"),
                "party": m.get("POLY_NM"),
                "district": m.get("ORIG_NM"),
                "committee": m.get("CMIT_NM"),
                "term": m.get("UNITS"),
                "reelection": m.get("REELE_GBN_NM"),
                "source_url": m.get("HOMEPAGE") or "https://open.assembly.go.kr",
                "updated_at": _now(),
            }
            db.collection(MEMBERS).document(mona).set(doc, merge=True)
            count += 1
        return {"success": True, "message": "의원 동기화 완료", "data": {"count": count}}


assembly_service = AssemblyService()
