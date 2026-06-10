from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from firebase_admin import firestore
from firebase.firebase_config import db

router = APIRouter()

class Comment(BaseModel):
    summaryId: str
    userId: str
    content: str

@router.get("/{summary_id}")
def get_comments(summary_id: str):
    docs = db.collection("comments").where("summaryId", "==", summary_id).stream()
    return [
        { "id": doc.id, **doc.to_dict() }
        for doc in docs
    ]

@router.post("")
def post_comment(comment: Comment):
    doc_ref = db.collection("comments").add({
        "summaryId": comment.summaryId,
        "userId": comment.userId,
        "content": comment.content,
        "createdAt": firestore.SERVER_TIMESTAMP,
    })
    return { "id": doc_ref[1].id, **comment.dict() }
