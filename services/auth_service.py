import os
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from passlib.context import CryptContext
from firebase.firebase_config import db
from models.model import UserCreate, UserLogin
import secrets
import string

class AuthService:

    # 보안 설정
    security = HTTPBearer()
    def __init__(self):
        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        self.secret_key = os.getenv("SECRET_KEY", self._generate_secret_key())
        self.algorithm = os.getenv("ALGORITHM", "HS256")
        self.access_token_expire_minutes = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

    def _generate_secret_key(self) -> str:
        """비밀 키 생성"""
        return ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """비밀번호 검증"""
        return self.pwd_context.verify(plain_password, hashed_password)

    def get_password_hash(self, password: str) -> str:
        """비밀번호 해싱"""
        return self.pwd_context.hash(password)

    def create_access_token(self, data: Dict[str, Any]) -> str:
        """JWT 액세스 토큰 생성"""
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(minutes=self.access_token_expire_minutes)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """JWT 토큰 검증"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except jwt.PyJWTError:
            return None
        
    def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security)) -> Dict[str, Any]:
        """JWT 토큰을 통한 현재 사용자 인증"""
        token = credentials.credentials
        payload = auth_service.verify_token(token)

        if payload is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user = auth_service.get_user_by_id(payload.get("sub"))
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        return user

    async def register_user(self, user_data: UserCreate) -> Dict[str, Any]:
        """사용자 회원가입"""
        try:
            # 이메일 중복 확인
            existing_user = await self.get_user_by_email(user_data.email)
            if existing_user:
                return {"success": False, "message": "이미 존재하는 이메일입니다."}

            # 비밀번호 해싱
            hashed_password = self.get_password_hash(user_data.password)

            # Firestore에 사용자 정보 저장
            user_doc = {
                "email": user_data.email,
                "password_hash": hashed_password,
                "phone": user_data.phone,
                "nick_name": user_data.nickname,
                "role": "user",
                "created_at": datetime.utcnow(),
                "interests": [],
                "notification_enabled": True,
                "avatar_url": None
            }

            # Firestore에 저장
            db.collection("users").document(user_data.email).set(user_doc)

            # 액세스 토큰 생성
            access_token = self.create_access_token({"sub": user_data.email})

            return {
                "success": True,
                "message": "회원가입이 완료되었습니다.",
                "data": {
                    "access_token": access_token,
                    "token_type": "bearer",
                    "user": {
                        "email": user_data.email,
                        "nickname": user_data.nickname,
                        "role": "user"
                    }
                }
            }

        except Exception as e:
            return {"success": False, "message": f"회원가입 중 오류가 발생했습니다: {str(e)}"}

    async def login_user(self, login_data: UserLogin) -> Dict[str, Any]:
        """사용자 로그인"""
        try:
            # 사용자 조회
            user = await self.get_user_by_email(login_data.email)
            if not user:
                return {"success": False, "message": "존재하지 않는 이메일입니다."}

            # 비밀번호 검증
            if not self.verify_password(login_data.password, user.get("password_hash")):
                return {"success": False, "message": "비밀번호가 올바르지 않습니다."}

            # 액세스 토큰 생성
            access_token = self.create_access_token({"sub": user["email"]})

            return {
                "success": True,
                "message": "로그인 성공",
                "data": {
                    "access_token": access_token,
                    "token_type": "bearer",
                    "user": {
                        "email": user["email"],
                        "nickname": user["nick_name"],
                        "role": user["role"],
                        "interests": user.get("interests", []),
                        "notification_enabled": user.get("notification_enabled", True),
                        "avatar_url": user.get("avatar_url"),
                        "created_at": user.get("created_at", datetime.utcnow()).isoformat(),
                    }
                }
            }

        except Exception as e:
            return {"success": False, "message": f"로그인 중 오류가 발생했습니다: {str(e)}"}

    async def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """이메일로 사용자 조회"""
        try:
            users_ref = db.collection("users")
            query = users_ref.where("email", "==", email)
            docs = query.stream()

            for doc in docs:
                return doc.to_dict()

            return None

        except Exception as e:
            print(f"사용자 조회 오류: {e}")
            return None

    async def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """사용자 ID로 사용자 조회"""
        try:
            doc_ref = db.collection("users").document(user_id)
            doc = doc_ref.get()

            if doc.exists:
                return doc.to_dict()

            return None

        except Exception as e:
            print(f"사용자 조회 오류: {e}")
            return None

    async def update_user_profile(self, user_id: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """사용자 프로필 업데이트"""
        try:
            # 업데이트할 데이터 준비
            update_fields = {}
            if "name" in update_data:
                update_fields["name"] = update_data["name"]
            if "interests" in update_data:
                update_fields["interests"] = update_data["interests"]
            if "notification_enabled" in update_data:
                update_fields["notification_enabled"] = update_data["notification_enabled"]
            if "avatar_url" in update_data:
                update_fields["avatar_url"] = update_data["avatar_url"]

            update_fields["updated_at"] = datetime.utcnow()

            # Firestore 업데이트
            doc_ref = db.collection("users").document(user_id)
            doc_ref.update(update_fields)

            return {"success": True, "message": "프로필이 업데이트되었습니다."}

        except Exception as e:
            return {"success": False, "message": f"프로필 업데이트 중 오류가 발생했습니다: {str(e)}"}
        

auth_service = AuthService()