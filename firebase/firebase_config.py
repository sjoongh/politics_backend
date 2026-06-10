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
            if firebase_admin._apps:
                self.app = firebase_admin.get_app()
            elif os.getenv("FIREBASE_PRIVATE_KEY"):
                # 환경변수(.env)에 키가 있으면 서비스계정 인증서로 초기화 (로컬 등)
                firebase_config = {
                    "type": os.getenv("FIREBASE_TYPE"),
                    "project_id": os.getenv("FIREBASE_PROJECT_ID"),
                    "private_key_id": os.getenv("FIREBASE_PRIVATE_KEY_ID"),
                    "private_key": os.getenv("FIREBASE_PRIVATE_KEY").replace("\\n", "\n"),
                    "client_email": os.getenv("FIREBASE_CLIENT_EMAIL"),
                    "client_id": os.getenv("FIREBASE_CLIENT_ID"),
                    "auth_uri": os.getenv("FIREBASE_AUTH_URI"),
                    "token_uri": os.getenv("FIREBASE_TOKEN_URI"),
                    "auth_provider_x509_cert_url": os.getenv("FIREBASE_AUTH_PROVIDER_X509_CERT_URL"),
                    "client_x509_cert_url": os.getenv("FIREBASE_CLIENT_X509_CERT_URL")
                }
                cred = credentials.Certificate(firebase_config)
                self.app = firebase_admin.initialize_app(cred)
            else:
                # 키 없으면 ADC(Application Default Credentials)로 초기화
                # Cloud Run 등에서 런타임 서비스계정 자동 사용 → 키 파일/환경변수 불필요
                self.app = firebase_admin.initialize_app()

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