import os
import uuid
from datetime import datetime
from typing import Optional

from firebase.firebase_config import db
from models.model import MemberCreate
from utils.member_rules import confirmed_records, criminal_count, has_missing_source, MEMBER_DISCLAIMER
from utils.member_stats import bill_stats, classify_status, status_label
from utils.member_vote import vote_label, vote_summary, merge_member_votes

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


    @staticmethod
    async def enrich_member_votes(num_bills: int = 20) -> dict:
        """최근 처리안건의 의원별 표결을 받아 각 의원에 누적(찬/반/기권/불참).
        codex: '주요 표결에서의 선택'이 핵심 책임성 지표. MONA_CD로 의원 매칭."""
        try:
            from services.assembly_client import fetch_rows, fetch_all
            # MONA_CD -> member doc id
            mona_map = {}
            for d in db.collection(COLLECTION).limit(500).stream():
                mid = d.to_dict().get("assembly_id")
                if mid:
                    mona_map[mid] = d.id
            # 이미 처리한 법안은 건너뜀(Firestore 쓰기 절약 + codex '새 법안만')
            meta = db.collection("_meta").document("voted_bills")
            done_bills = set((meta.get().to_dict() or {}).get("ids") or [])
            bills = fetch_rows("ncocpgfiaoituanbr", {"AGE": ASSEMBLY_AGE}, p_index=1, p_size=num_bills)
            new_bill_ids = []
            per_member = {}   # member_id -> [vote dict]
            for b in bills:
                bid = b.get("BILL_ID")
                if not bid or bid in done_bills:
                    continue
                new_bill_ids.append(bid)
                rows = fetch_all("nojepdqqaweusdfbi", {"AGE": ASSEMBLY_AGE, "BILL_ID": bid},
                                 p_size=300, max_pages=2)
                for r in rows:
                    mid = mona_map.get(r.get("MONA_CD"))
                    if not mid:
                        continue
                    per_member.setdefault(mid, []).append({
                        "bill_id": bid,
                        "bill": r.get("BILL_NAME"),
                        "vote": vote_label(r.get("RESULT_VOTE_MOD")),
                        "date": (r.get("VOTE_DATE") or "").split(" ")[0],
                        "link": r.get("BILL_URL"),
                    })
            updated = 0
            for mid, new_votes in per_member.items():
                doc = db.collection(COLLECTION).document(mid)
                existing = doc.get().to_dict().get("votes") or []
                merged = merge_member_votes(existing, new_votes, cap=30)
                doc.update({"votes": merged, "vote_summary": vote_summary(merged),
                            "updated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")})
                updated += 1
            if new_bill_ids:
                meta.set({"ids": list(done_bills | set(new_bill_ids))[-500:]})
            return {"success": True, "message": "의원 표결 수집",
                    "data": {"new_bills": len(new_bill_ids), "members_updated": updated}}
        except Exception as e:
            print(f"[enrich_member_votes] {e!r}")
            return {"success": False, "message": "의원 표결 수집 실패"}


member_service = MemberService()
