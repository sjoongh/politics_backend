from datetime import datetime
from firebase.firebase_config import db
from google.cloud import firestore
from models.model import BookmarkBase

class BookmarkService:
    def add_bookmark(user_id: str, bookmark_data: BookmarkBase):
        bookmark_id = f"bookmark_{user_id}_{bookmark_data.article_id}"

        bookmark = {
            "id": bookmark_id,
            "user_id": user_id,
            "article_id": bookmark_data.article_id,
            "created_at": datetime.utcnow()
        }

        db.collection("bookmarks").document(bookmark_id).set(bookmark)
        return bookmark

    def get_bookmarks(user_id: str, limit: int = 20):
        bookmarks_ref = db.collection("bookmarks")
        query = bookmarks_ref.where("user_id", "==", user_id)
        query = query.order_by("created_at", direction=firestore.Query.DESCENDING).limit(limit)

        docs = query.stream()
        bookmarks = [doc.to_dict() for doc in docs]
        return bookmarks

bookmark_service = BookmarkService()