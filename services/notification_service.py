from datetime import datetime
from typing import Dict, Any, Optional
from firebase.firebase_config import db
from google.cloud import firestore
from models.enum import NotificationPriority
from models.model import NotificationCreate

class NotificationService:
    def __init__(self):
        self.priority_weights = {
            NotificationPriority.LOW: 1,
            NotificationPriority.MEDIUM: 2,
            NotificationPriority.HIGH: 3
        }

    async def create_notification(self, notification_data: NotificationCreate) -> Dict[str, Any]:
        """알림 생성"""
        try:
            notifications_created = []

            for user_id in notification_data.user_ids:
                notification_id = f"notif_{user_id}_{int(datetime.utcnow().timestamp() * 1000)}"

                notification = {
                    "id": notification_id,
                    "user_id": user_id,
                    "title": notification_data.title,
                    "message": notification_data.message,
                    "priority": notification_data.priority.value,
                    "category": notification_data.category.value,
                    "article_id": notification_data.article_id,
                    "is_read": False,
                    "created_at": datetime.utcnow()
                }

                # Firestore에 저장
                db.collection("notifications").document(notification_id).set(notification)
                notifications_created.append(notification)

                # 실시간 알림 전송 (FCM 시뮬레이션)
                await self._send_real_time_notification(user_id, notification)

            return {
                "success": True,
                "message": f"{len(notifications_created)}개의 알림이 생성되었습니다.",
                "data": {"notifications": notifications_created}
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"알림 생성 중 오류가 발생했습니다: {str(e)}"
            }

    async def _send_real_time_notification(self, user_id: str, notification: Dict[str, Any]):
        """실시간 알림 전송 (FCM 시뮬레이션)"""
        try:
            # 실제 FCM 구현 시 여기에 FCM 전송 로직 추가
            print(f"[FCM] 사용자 {user_id}에게 알림 전송: {notification['title']}")

            # 사용자별 알림 설정 확인
            user_settings = await self._get_user_notification_settings(user_id)
            if not user_settings.get("notification_enabled", True):
                return

            # 우선순위별 알림 전송 방식 결정
            priority = notification["priority"]
            if priority == NotificationPriority.HIGH.value:
                # 높은 우선순위: 즉시 푸시 알림
                await self._send_push_notification(user_id, notification)
            elif priority == NotificationPriority.MEDIUM.value:
                # 중간 우선순위: 배치 알림
                await self._queue_batch_notification(user_id, notification)

        except Exception as e:
            print(f"실시간 알림 전송 오류: {e}")

    async def _get_user_notification_settings(self, user_id: str) -> Dict[str, Any]:
        """사용자 알림 설정 조회"""
        try:
            doc_ref = db.collection("users").document(user_id)
            doc = doc_ref.get()

            if doc.exists:
                user_data = doc.to_dict()
                return {
                    "notification_enabled": user_data.get("notification_enabled", True),
                    "interests": user_data.get("interests", [])
                }

            return {"notification_enabled": True, "interests": []}

        except Exception as e:
            print(f"사용자 알림 설정 조회 오류: {e}")
            return {"notification_enabled": True, "interests": []}

    async def _send_push_notification(self, user_id: str, notification: Dict[str, Any]):
        """푸시 알림 전송 (FCM)"""
        # 실제 FCM 구현 예시
        # from firebase_admin import messaging
        # 
        # message = messaging.Message(
        #     notification=messaging.Notification(
        #         title=notification["title"],
        #         body=notification["message"]
        #     ),
        #     token=user_fcm_token,  # 사용자의 FCM 토큰
        #     data={
        #         "notification_id": notification["id"],
        #         "article_id": notification.get("article_id", ""),
        #         "category": notification["category"]
        #     }
        # )
        # 
        # response = messaging.send(message)
        print(f"[PUSH] 푸시 알림 전송: {notification['title']}")

    async def _queue_batch_notification(self, user_id: str, notification: Dict[str, Any]):
        """배치 알림 큐에 추가"""
        print(f"[BATCH] 배치 알림 큐에 추가: {notification['title']}")

    async def get_user_notifications(self, 
                                   user_id: str, 
                                   is_read: Optional[bool] = None,
                                   limit: int = 20) -> Dict[str, Any]:
        """사용자 알림 목록 조회"""
        try:
            notifications_ref = db.collection("notifications")
            query = notifications_ref.where("user_id", "==", user_id)

            if is_read is not None:
                query = query.where("is_read", "==", is_read)

            query = query.order_by("created_at", direction=firestore.Query.DESCENDING).limit(limit)

            docs = query.stream()
            notifications = [doc.to_dict() for doc in docs]

            # 읽지 않은 알림 개수 계산
            unread_count = await self._get_unread_count(user_id)

            return {
                "success": True,
                "data": {
                    "notifications": notifications,
                    "unread_count": unread_count,
                    "total_count": len(notifications)
                }
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"알림 조회 중 오류가 발생했습니다: {str(e)}"
            }

    async def _get_unread_count(self, user_id: str) -> int:
        """읽지 않은 알림 개수 조회"""
        try:
            notifications_ref = db.collection("notifications")
            query = notifications_ref.where("user_id", "==", user_id).where("is_read", "==", False)

            docs = list(query.stream())
            return len(docs)

        except Exception as e:
            print(f"읽지 않은 알림 개수 조회 오류: {e}")
            return 0

    async def mark_notification_as_read(self, notification_id: str, user_id: str) -> Dict[str, Any]:
        """알림을 읽음으로 표시"""
        try:
            doc_ref = db.collection("notifications").document(notification_id)
            doc = doc_ref.get()

            if not doc.exists:
                return {"success": False, "message": "알림을 찾을 수 없습니다."}

            notification = doc.to_dict()

            # 사용자 권한 확인
            if notification["user_id"] != user_id:
                return {"success": False, "message": "알림에 접근할 권한이 없습니다."}

            # 읽음 상태 업데이트
            doc_ref.update({"is_read": True, "read_at": datetime.utcnow()})

            return {"success": True, "message": "알림이 읽음으로 표시되었습니다."}

        except Exception as e:
            return {"success": False, "message": f"알림 상태 업데이트 중 오류가 발생했습니다: {str(e)}"}

    async def mark_all_notifications_as_read(self, user_id: str) -> Dict[str, Any]:
        """모든 알림을 읽음으로 표시"""
        try:
            notifications_ref = db.collection("notifications")
            query = notifications_ref.where("user_id", "==", user_id).where("is_read", "==", False)

            docs = query.stream()
            updated_count = 0

            for doc in docs:
                doc.reference.update({"is_read": True, "read_at": datetime.utcnow()})
                updated_count += 1

            return {
                "success": True,
                "message": f"{updated_count}개의 알림이 읽음으로 표시되었습니다."
            }

        except Exception as e:
            return {"success": False, "message": f"알림 일괄 업데이트 중 오류가 발생했습니다: {str(e)}"}

    async def create_breaking_news_notification(self, article: Dict[str, Any]) -> Dict[str, Any]:
        """속보 알림 생성"""
        try:
            # 모든 사용자에게 속보 알림 전송 (실제로는 구독자만)
            users_ref = db.collection("users")
            users_query = users_ref.where("notification_enabled", "==", True)

            user_docs = users_query.stream()
            user_ids = [doc.id for doc in user_docs]

            if not user_ids:
                return {"success": False, "message": "알림을 받을 사용자가 없습니다."}

            notification_data = NotificationCreate(
                title="🚨 정치 속보",
                message=f"{article['title']}",
                priority=NotificationPriority.HIGH,
                category=article['category'],
                user_ids=user_ids,
                article_id=article['id']
            )

            return await self.create_notification(notification_data)

        except Exception as e:
            return {"success": False, "message": f"속보 알림 생성 중 오류가 발생했습니다: {str(e)}"}

# 알림 서비스 인스턴스 생성
notification_service = NotificationService()