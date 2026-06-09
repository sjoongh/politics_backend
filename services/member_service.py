import uuid
from datetime import datetime
from typing import Optional

from firebase.firebase_config import db
from models.model import MemberCreate
from utils.member_rules import confirmed_records, criminal_count, has_missing_source, MEMBER_DISCLAIMER

COLLECTION = "members"


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


member_service = MemberService()
