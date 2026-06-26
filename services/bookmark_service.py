from datetime import datetime
from firebase.firebase_config import db
from google.cloud import firestore
from models.model import BookmarkBase

class BookmarkService:
    def add_bookmark(self, user_id: str, bookmark_data: BookmarkBase):
        bookmark_id = f"bookmark_{user_id}_{bookmark_data.article_id}"

        bookmark = {
            "id": bookmark_id,
            "user_id": user_id,
            "article_id": bookmark_data.article_id,
            "created_at": datetime.utcnow()
        }

        db.collection("bookmarks").document(bookmark_id).set(bookmark)
        return bookmark

    def get_bookmarks(self, user_id: str, limit: int = 20):
        # 단일 필터(복합 인덱스 불필요) 후 파이썬에서 최신순 정렬 — Firestore composite index 없이 동작
        bookmarks_ref = db.collection("bookmarks")
        docs = bookmarks_ref.where("user_id", "==", user_id).limit(200).stream()
        bookmarks = sorted((d.to_dict() for d in docs),
                           key=lambda b: str(b.get("created_at") or ""), reverse=True)
        return bookmarks[:limit]

bookmark_service = BookmarkService()