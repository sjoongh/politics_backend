from firebase.firebase_config import db
from models.model import Summary
from collections import Counter

def add_summary(summary: Summary):
    db.collection("summaries").add(summary.dict())
    if summary.tags:
        db.collection("notifications").add({
            "message": f"'{summary.tags[0]}' 관련 요약이 추가되었습니다.",
            "tags": summary.tags,
            "read": False,
            "createdAt": summary.createdAt
        })
    return {"message": "요약 저장됨"}

def search_summaries(keyword: str, tag: str):
    results = []
    ref = db.collection("summaries")
    docs = ref.where("tags", "array_contains", tag).stream() if tag else ref.stream()

    for doc in docs:
        data = doc.to_dict()
        if (keyword and keyword in data.get("title", "")) or tag:
            data["id"] = doc.id
            results.append(data)
    return results

def get_today_summaries():
    docs = db.collection("summaries").limit(10).stream()
    return [doc.to_dict() for doc in docs]

def get_tag_statistics():
    docs = db.collection("summaries").stream()
    tag_list = []
    for doc in docs:
        tag_list.extend(doc.to_dict().get("tags", []))
    count = Counter(tag_list)
    return [{"tag": k, "count": v} for k, v in count.items()]

