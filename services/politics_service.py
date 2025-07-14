from firebase.firebase_config import db

class PoliticsService:

    @staticmethod
    async def get_president_info():
        doc = db.collection("politics").document("president").get()
        if doc.exists:
            return doc.to_dict()
        return {}

    @staticmethod
    async def get_recent_policies():
        docs = db.collection("policies").order_by("published_at", direction="DESCENDING").limit(10).stream()
        return [doc.to_dict() for doc in docs]

    @staticmethod
    async def get_parliamentary_activities():
        docs = db.collection("parliament_activities").order_by("date", direction="DESCENDING").limit(10).stream()
        return [doc.to_dict() for doc in docs]

    @staticmethod
    async def get_political_statements():
        docs = db.collection("statements").order_by("timestamp", direction="DESCENDING").limit(10).stream()
        return [doc.to_dict() for doc in docs]

politics_service = PoliticsService()