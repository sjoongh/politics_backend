import uuid
from datetime import datetime

from firebase.firebase_config import db
from models.model import IssueSeed, EventSeed
from utils.issue_rules import (
    is_valid_status, to_summary, sort_events, article_public, patchable,
)

COLLECTION = "issues"


def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


class IssueService:
    @staticmethod
    async def create(seed: IssueSeed) -> dict:
        if not is_valid_status(seed.status):
            return {"success": False, "message": "잘못된 상태입니다."}
        issue_id = uuid.uuid4().hex
        now = _now()
        data = {
            **seed.dict(),
            "id": issue_id,
            "slug": seed.slug or issue_id,
            "started_at": now,
            "updated_at": now,
            "events": [],
            "article_ids": [],
        }
        db.collection(COLLECTION).document(issue_id).set(data)
        return {"success": True, "message": "이슈 생성 성공", "data": data}

    @staticmethod
    async def list_summaries(status=None, category=None, limit: int = 20, offset: int = 0) -> dict:
        query = db.collection(COLLECTION)
        if status:
            query = query.where("status", "==", status)
        if category:
            query = query.where("category", "==", category)
        query = query.limit(limit).offset(offset)
        items = [to_summary({**doc.to_dict(), "id": doc.id}) for doc in query.stream()]
        return {"success": True, "message": "이슈 목록 조회 성공", "data": items}

    @staticmethod
    async def get_detail(issue_id: str) -> dict:
        doc = db.collection(COLLECTION).document(issue_id).get()
        if not doc.exists:
            return {"success": False, "message": "이슈를 찾을 수 없습니다."}
        issue = doc.to_dict()
        issue["id"] = doc.id
        issue["events"] = sort_events(issue.get("events", []))
        articles = []
        for aid in issue.get("article_ids", []):
            adoc = db.collection("articles").document(aid).get()
            if adoc.exists:
                articles.append(article_public(adoc.to_dict()))
        issue["articles"] = articles
        return {"success": True, "message": "이슈 상세 조회 성공", "data": issue}

    @staticmethod
    async def update(issue_id: str, fields: dict) -> dict:
        if "status" in (fields or {}) and not is_valid_status(fields["status"]):
            return {"success": False, "message": "잘못된 상태입니다."}
        ref = db.collection(COLLECTION).document(issue_id)
        if not ref.get().exists:
            return {"success": False, "message": "이슈를 찾을 수 없습니다."}
        safe = patchable(fields)
        safe["updated_at"] = _now()
        ref.update(safe)
        return {"success": True, "message": "이슈 수정 성공", "data": ref.get().to_dict()}

    @staticmethod
    async def add_event(issue_id: str, seed: EventSeed) -> dict:
        ref = db.collection(COLLECTION).document(issue_id)
        snap = ref.get()
        if not snap.exists:
            return {"success": False, "message": "이슈를 찾을 수 없습니다."}
        event = {**seed.dict(), "id": uuid.uuid4().hex}
        events = list(snap.to_dict().get("events", [])) + [event]
        ref.update({"events": events, "updated_at": _now()})
        return {"success": True, "message": "이벤트 추가 성공", "data": ref.get().to_dict()}

    @staticmethod
    async def add_articles(issue_id: str, article_ids) -> dict:
        ref = db.collection(COLLECTION).document(issue_id)
        snap = ref.get()
        if not snap.exists:
            return {"success": False, "message": "이슈를 찾을 수 없습니다."}
        existing = list(snap.to_dict().get("article_ids", []))
        for aid in (article_ids or []):
            if aid not in existing:
                existing.append(aid)
        ref.update({"article_ids": existing, "updated_at": _now()})
        return {"success": True, "message": "기사 연결 성공", "data": ref.get().to_dict()}


issue_service = IssueService()
