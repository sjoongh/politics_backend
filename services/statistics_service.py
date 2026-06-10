# services/summary_service.py
from datetime import datetime, timedelta
from firebase.firebase_config import db

class StatisticsService:
    async def get_statistics_data(self):
        articles_ref = db.collection("articles")
        users_ref = db.collection("users")

        # 전체 기사 수
        total_articles = len(list(articles_ref.stream()))

        # 오늘 기사 수
        today = datetime.now().strftime("%Y-%m-%d")
        start_date = datetime.strptime(today, "%Y-%m-%d")
        end_date = start_date + timedelta(days=1)

        today_query = articles_ref.where("published_at", ">=", start_date).where("published_at", "<", end_date)
        today_articles = len(list(today_query.stream()))

        # 전체 사용자 수
        total_users = len(list(users_ref.stream()))

        return {
            "total_articles": total_articles,
            "today_articles": today_articles,
            "total_users": total_users,
            "last_updated": datetime.utcnow().isoformat()
        }

statistics_service = StatisticsService()