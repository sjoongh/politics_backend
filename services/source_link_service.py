"""source_item ↔ issue 연결: 자동(고신뢰) + 검수 큐(애매) 하이브리드."""
from datetime import datetime, timezone
from firebase.firebase_config import db
from utils.issue_linker import best_issue


def _now():
    return datetime.now(timezone.utc).isoformat()


class SourceLinkService:
    async def link_unlinked(self, limit: int = 200) -> dict:
        """미연결(link_status='new') 소스를 이슈에 자동 연결하거나 검수 큐로."""
        try:
            issues = [d.to_dict() for d in db.collection("issues").stream()]
            n_auto = n_pending = 0
            docs = db.collection("source_items").where("link_status", "==", "new").limit(limit).stream()
            for doc in docs:
                s = doc.to_dict()
                iss, score, status = best_issue(s, issues)
                if status == "auto" and iss:
                    doc.reference.update({"issue_id": iss["id"], "link_status": "auto", "updated_at": _now()})
                    n_auto += 1
                elif status == "pending" and iss:
                    doc.reference.update({"issue_id": iss["id"], "link_status": "pending", "updated_at": _now()})
                    n_pending += 1
                # 점수 미달은 'new' 유지(다음 이슈 생성 후 재시도 가능)
            return {"success": True, "message": "연결 완료", "data": {"auto": n_auto, "pending": n_pending}}
        except Exception as e:
            print(f"[link_unlinked] {e!r}")
            return {"success": False, "message": "연결 실패"}

    async def list_pending(self, limit: int = 50) -> dict:
        try:
            docs = db.collection("source_items").where("link_status", "==", "pending").limit(limit).stream()
            items = [d.to_dict() for d in docs]
            return {"success": True, "message": "검수 대기", "data": {"items": items, "count": len(items)}}
        except Exception as e:
            print(f"[list_pending] {e!r}")
            return {"success": False, "message": "검수 목록 조회 실패"}

    async def review(self, source_id: str, action: str, issue_id: str = None) -> dict:
        """관리자 검수: confirm(승인) / reject(거부)."""
        ref = db.collection("source_items").document(source_id)
        if not ref.get().exists:
            return {"success": False, "message": "소스를 찾을 수 없습니다."}
        if action == "confirm":
            patch = {"link_status": "confirmed", "updated_at": _now()}
            if issue_id:
                patch["issue_id"] = issue_id
            ref.update(patch)
        elif action == "reject":
            ref.update({"link_status": "rejected", "issue_id": None, "updated_at": _now()})
        else:
            return {"success": False, "message": "action은 confirm|reject"}
        return {"success": True, "message": "검수 반영"}


source_link_service = SourceLinkService()
