from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from firebase_admin import firestore

router = APIRouter()
db = firestore.client()

class Feedback(BaseModel):
    summaryId: str
    type: str
    comment: str

@router.post("")
async def submit_feedback(feedback: Feedback):
    try:
        db.collection("feedback").add({
            "summaryId": feedback.summaryId,
            "type": feedback.type,
            "comment": feedback.comment,
            "createdAt": firestore.SERVER_TIMESTAMP,
        })
        return {"message": "피드백 저장 완료"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
