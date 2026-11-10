"""판(edition) 문서 생성·조회. 오늘(KST) 판만 쓰고 지난 날짜 판은 고정한다."""
from datetime import datetime, timedelta, timezone
from firebase.firebase_config import db
from utils.edition import build_edition, kst_date, KST
from utils.issue_rules import to_summary

COLLECTION = "editions"


class EditionService:
    @staticmethod
    def today() -> str:
        return datetime.now(KST).strftime("%Y-%m-%d")

    def build(self, date=None, issues=None, sources=None, ctx=None) -> dict:
        date = date or self.today()
        if date != self.today():
            raise ValueError("지난 날짜 판은 다시 쓰지 않는다")
        if issues is None:
            issues = ctx.active_issues() if ctx else [
                {**d.to_dict(), "id": d.id} for d in db.collection("issues").stream()
                if d.to_dict().get("active") is not False]
        if sources is None:
            if ctx:
                sources = ctx.recent_sources(3)
            else:
                cutoff = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%d")
                from google.cloud import firestore as _fs
                sources = [{**d.to_dict(), "id": d.id} for d in db.collection("source_items")
                           .where("published_at", ">=", cutoff)
                           .order_by("published_at", direction=_fs.Query.DESCENDING).limit(400).stream()]
        overview = None
        try:
            snap = db.collection("daily_summaries").document(date).get()
            if snap.exists:
                overview = (snap.to_dict() or {}).get("overview")
        except Exception:  # noqa: BLE001
            overview = None
        edition = build_edition(date, issues, sources, overview)
        db.collection(COLLECTION).document(date).set(edition)
        return {"success": True, "message": "판 생성",
                "data": {"date": date, "top": len(edition["top_issues"]), "votes": len(edition["assembly"]["votes"]),
                         "bills": len(edition["assembly"]["bills"]), "gov": len(edition["government"]),
                         "others": len(edition["other_issue_ids"])}}

    def get(self, date: str) -> dict:
        snap = db.collection(COLLECTION).document(date).get()
        if not snap.exists:
            return {"success": True, "message": "판 없음", "data": {"edition": None, "other_issues": []}}
        edition = snap.to_dict()
        others = []
        ids = edition.get("other_issue_ids") or []
        if ids:
            refs = [db.collection("issues").document(i) for i in ids]
            by = {d.id: {**d.to_dict(), "id": d.id} for d in db.get_all(refs) if d.exists}
            others = [to_summary(by[i]) for i in ids if i in by and by[i].get("active") is not False]
        return {"success": True, "message": "판 조회", "data": {"edition": edition, "other_issues": others}}


edition_service = EditionService()
