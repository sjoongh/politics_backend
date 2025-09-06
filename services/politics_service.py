from firebase.firebase_config import db
from models.model import ParliamentaryActivity
from models.model import PoliticalStatement

class PoliticsService:

    @staticmethod
    async def get_president_info():
        docs = db.collection("presidents").order_by("date", direction="DESCENDING").limit(10).stream()
        return [doc.to_dict() for doc in docs]

    @staticmethod
    async def get_recent_policies():
        docs = db.collection("parliamentary_activities").order_by("date", direction="DESCENDING").limit(10).stream()
        return [doc.to_dict() for doc in docs]

    @staticmethod
    async def get_parliamentary_activities():
        docs = db.collection("policies").order_by("date", direction="DESCENDING").limit(10).stream()
        print("Retrieved parliamentary activities:", docs)
        return [doc.to_dict() for doc in docs]

    @staticmethod
    async def get_political_statements():
        docs = db.collection("political_statements").order_by("date", direction="DESCENDING").limit(10).stream()
        return [doc.to_dict() for doc in docs]
    
    @staticmethod
    async def save_parliamentary_activity(activity: ParliamentaryActivity):
        doc_ref = db.collection("parliamentary_activities").document()
        doc_ref.set(activity.dict())
        return {"id": doc_ref.id, "message": "Parliamentary activity saved successfully"}
    
    @staticmethod
    async def save_political_statement(statement: PoliticalStatement):
        doc_ref = db.collection("political_statements").document()
        doc_ref.set(statement.dict())
        return {"id": doc_ref.id, "message": "Political statement saved successfully"}

politics_service = PoliticsService()