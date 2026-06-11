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

    @staticmethod
    async def sync_bills(max_pages: int = 5) -> dict:
        rows = []
        for i in range(1, max_pages + 1):
            page = fetch_rows("nzmimeepazxkubdpn", params={"AGE": AGE}, p_index=i, p_size=100)
            if not page:
                break
            rows.extend(page)
        # 대표발의자(RST_MONA_CD)별로 묶기
        by_member = {}
        for b in rows:
            mona = b.get("RST_MONA_CD")
            if not mona:
                continue
            by_member.setdefault(mona, []).append({
                "name": b.get("BILL_NAME"),
                "no": b.get("BILL_NO"),
                "date": b.get("PROPOSE_DT"),
                "result": b.get("PROC_RESULT"),
                "link": b.get("DETAIL_LINK"),
            })
        count = 0
        for mona, bills in by_member.items():
            ref = db.collection(MEMBERS).document(mona)
            if not ref.get().exists:
                continue
            ref.update({"bills": bills[:30], "bill_count": len(bills), "updated_at": _now()})
            count += 1
        return {"success": True, "message": "발의법안 동기화 완료", "data": {"members_updated": count}}

    @staticmethod
    async def sync_votes(num_bills: int = 10) -> dict:
        bills = fetch_rows("ncocpgfiaoituanbr", params={"AGE": AGE}, p_index=1, p_size=num_bills)
        if not bills:
            return {"success": False, "message": "표결 안건을 가져오지 못했습니다."}
        votes_by_member = {}
        for b in bills:
            bid = b.get("BILL_ID")
            if not bid:
                continue
            rows = fetch_all("nojepdqqaweusdfbi", params={"AGE": AGE, "BILL_ID": bid}, p_size=300, max_pages=2)
            for v in rows:
                mona = v.get("MONA_CD")
                if not mona:
                    continue
                votes_by_member.setdefault(mona, []).append({
                    "bill": v.get("BILL_NAME"),
                    "vote": v.get("RESULT_VOTE_MOD"),
                    "date": v.get("VOTE_DATE"),
                    "link": v.get("BILL_URL"),
                })
        count = 0
        for mona, votes in votes_by_member.items():
            ref = db.collection(MEMBERS).document(mona)
            if not ref.get().exists:
                continue
            ref.update({"votes": votes[:30], "updated_at": _now()})
            count += 1
        return {"success": True, "message": "표결 동기화 완료", "data": {"members_updated": count, "bills": len(bills)}}


assembly_service = AssemblyService()
