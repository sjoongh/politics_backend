import os
import uuid
from datetime import datetime
from typing import Optional

from firebase.firebase_config import db
from models.model import MemberCreate
from utils.member_rules import confirmed_records, criminal_count, has_missing_source, MEMBER_DISCLAIMER
from utils.member_stats import bill_stats, classify_status, status_label

COLLECTION = "members"
ASSEMBLY_AGE = os.getenv("ASSEMBLY_AGE", "22")


class MemberService:
    @staticmethod
    async def upsert_member(member: MemberCreate) -> dict:
        records = [r.dict() for r in member.criminal_records]
        if has_missing_source(records):
            return {"success": False, "message": "모든 전과 항목에 출처(source_url)가 필요합니다."}
        member_id = uuid.uuid4().hex
        data = member.dict()
        data["criminal_records"] = records
        data["id"] = member_id
        data["updated_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        db.collection(COLLECTION).document(member_id).set(data)
        return {"success": True, "message": "의원 정보 저장 성공", "data": {"member": data}}

    @staticmethod
    async def list_members(party: Optional[str] = None, limit: int = 20, offset: int = 0) -> dict:
        ref = db.collection(COLLECTION)
        query = ref.where("party", "==", party) if party else ref
        query = query.limit(limit).offset(offset)
        members = []
        for doc in query.stream():
            m = doc.to_dict()
            members.append({
                "id": doc.id,
                "name": m.get("name"),
                "party": m.get("party"),
                "district": m.get("district"),
                "committee": m.get("committee"),
                "term": m.get("term"),
                "photo_url": m.get("photo_url"),
                "criminal_count": criminal_count(m.get("criminal_records")),
            })
        return {"success": True, "message": "의원 목록 조회 성공", "data": {"members": members, "count": len(members)}}

    @staticmethod
    async def get_member(member_id: str) -> dict:
        doc = db.collection(COLLECTION).document(member_id).get()
        if not doc.exists:
            return {"success": False, "message": "의원을 찾을 수 없습니다."}
        m = doc.to_dict()
        m["id"] = doc.id
        m["criminal_records"] = confirmed_records(m.get("criminal_records"))  # 확정만 노출
        m["disclaimer"] = MEMBER_DISCLAIMER
        return {"success": True, "message": "의원 상세 조회 성공", "data": {"member": m}}


    @staticmethod
    async def enrich_member_bills(limit: int = 60) -> dict:
        """의원별 대표발의 법안(RST_MONA_CD)을 받아 처리흐름 통계와 함께 저장.
        codex: 발의 '수'가 아니라 통과/대안반영/심사중 흐름. MONA_CD 기준(이름 매칭 금지)."""
        try:
            from services.assembly_client import fetch_rows
            targets = [{**d.to_dict(), "id": d.id} for d in db.collection(COLLECTION).limit(500).stream()
                       if d.to_dict().get("assembly_id") and not d.to_dict().get("bills_synced")][:limit]
            done = 0
            for m in targets:
                rows = fetch_rows("nzmimeepazxkubdpn",
                                  {"AGE": ASSEMBLY_AGE, "RST_MONA_CD": m["assembly_id"]},
                                  p_index=1, p_size=100)
                bills = [{
                    "name": b.get("BILL_NAME"),
                    "status": status_label(b.get("PROC_RESULT")),
                    "outcome": classify_status(b.get("PROC_RESULT")),
                    "date": b.get("PROPOSE_DT"),
                    "url": b.get("DETAIL_LINK"),
                } for b in rows]
                db.collection(COLLECTION).document(m["id"]).update({
                    "bills": bills[:30],
                    "bill_stats": bill_stats(rows),
                    "bills_synced": True,
                    "updated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                })
                done += 1
            return {"success": True, "message": "의원 발의법안 수집", "data": {"enriched": done}}
        except Exception as e:
            print(f"[enrich_member_bills] {e!r}")
            return {"success": False, "message": "의원 발의법안 수집 실패"}


member_service = MemberService()
