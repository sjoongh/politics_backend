import os
import firebase_admin
from firebase_admin import credentials, firestore, auth
from dotenv import load_dotenv

load_dotenv()

class FirebaseConfig:
    def __init__(self):
        self.app = None
        self.db = None
        self._initialize_firebase()

    def _initialize_firebase(self):
        try:
            # Firebase 서비스 계정 정보를 환경 변수에서 가져오기
            cred_path = os.getenv("FIREBASE_CREDENTIAL_PATH")

            # 자격 증명 객체 생성
            cred = credentials.Certificate(cred_path)

            # Firebase 앱 초기화 (이미 초기화된 경우 건너뛰기)
            if not firebase_admin._apps:
                self.app = firebase_admin.initialize_app(cred)
            else:
                self.app = firebase_admin.get_app()

            # Firestore 클라이언트 초기화
            self.db = firestore.client()

            print("Firebase 초기화 완료")

        except Exception as e:
            print(f"Firebase 초기화 오류: {e}")
            raise e

    def get_firestore_client(self):
        """Firestore 클라이언트 반환"""
        return self.db

    def get_auth_client(self):
        """Firebase Auth 클라이언트 반환"""
        return auth

# 싱글톤 패턴으로 Firebase 인스턴스 생성
firebase_instance = FirebaseConfig()
db = firebase_instance.get_firestore_client()
firebase_auth = firebase_instance.get_auth_client()