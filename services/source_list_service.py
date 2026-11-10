"""공개 소스 목록(둘러보기): 유형별 published_at 역순 커서 페이지. 표시 필드만 내보낸다."""
from firebase.firebase_config import db
from utils.cursor import encode_cursor, decode_cursor

TYPES = ("assembly_vote", "assembly_bill", "gov_policy")
PUBLIC_KEYS = ("id", "type", "title", "law_name", "published_at", "procedural", "url")


def _row(s: dict) -> dict:
    row = {k: s.get(k) for k in PUBLIC_KEYS}
    row["issue_ids"] = list(s.get("issue_ids") or (
        [s["issue_id"]] if s.get("issue_id") and s.get("link_status") in ("auto", "confirmed") else []))
    if s.get("vote"):
        v = s["vote"]
        row["vote"] = {k: v.get(k) for k in ("yes", "no", "abstain", "result")}
    return row


class SourceListService:
    @staticmethod
    def list(type_: str, cursor, limit: int = 30) -> dict:
        from google.cloud import firestore as _fs
        if type_ not in TYPES:
            return {"success": False, "message": "type은 assembly_vote|assembly_bill|gov_policy"}
        limit = max(1, min(int(limit or 30), 100))
        q = (db.collection("source_items").where("type", "==", type_)
             .order_by("published_at", direction=_fs.Query.DESCENDING).order_by("__name__"))
        cur = decode_cursor(cursor)
        if "p" in cur and "i" in cur:
            q = q.start_after([cur["p"], cur["i"]])
        snaps = list(q.limit(limit + 1).stream())
        rows = [{**d.to_dict(), "id": d.id} for d in snaps[:limit]]
        nxt = None
        if len(snaps) > limit and rows:
            last = rows[-1]
            nxt = encode_cursor({"p": last.get("published_at"), "i": last["id"]})
        return {"success": True, "message": "소스 목록", "data": {"items": [_row(r) for r in rows], "next_cursor": nxt}}


source_list_service = SourceListService()
