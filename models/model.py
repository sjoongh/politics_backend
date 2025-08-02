from pydantic import BaseModel, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime
from models.enum import ArticleCategory, NotificationPriority, UserRole

# 사용자 관련 모델
class UserBase(BaseModel):
    email: EmailStr = None
    role: UserRole = UserRole.USER
 
class UserCreate(BaseModel):
    email: Optional[str] = None
    password: Optional[str] = None
    nickname: Optional[str] = None
    phone: Optional[str] = None
    

class UserUpdate(BaseModel):
    interests: Optional[List[str]] = None
    notification_enabled: Optional[bool] = None

class PasswordChangeRequest(BaseModel):
    password: str
    email: Optional[str] = None

class User(UserBase):
    uid: str
    created_at: datetime
    interests: List[str] = []
    notification_enabled: bool = True
    avatar_url: Optional[str] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

# 뉴스 기사 관련 모델
class ArticleBase(BaseModel):
    title: str
    ai_summary: str
    source: str
    source_url: str
    category: ArticleCategory
    keywords: List[str] = []

class ArticleCreate(ArticleBase):
    pass

class Article(ArticleBase):
    id: str
    published_at: datetime
    created_at: datetime
    updated_at: datetime
    view_count: int = 0
    bookmark_count: int = 0

# 알림 관련 모델
class NotificationBase(BaseModel):
    title: str
    message: str
    priority: NotificationPriority
    category: ArticleCategory

class NotificationCreate(NotificationBase):
    user_ids: List[str]
    article_id: Optional[str] = None

class Notification(NotificationBase):
    id: str
    user_id: str
    article_id: Optional[str] = None
    is_read: bool = False
    created_at: datetime

# 오늘의 요약 관련 모델
class DailySummaryBase(BaseModel):
    date: str  # YYYY-MM-DD 형식
    highlights: List[str]
    major_events: List[Dict[str, Any]]
    categories: Dict[str, List[Dict[str, Any]]]

class DailySummary(DailySummaryBase):
    id: str
    created_at: datetime
    updated_at: datetime

# 북마크 관련 모델
class BookmarkBase(BaseModel):
    article_id: str

class Bookmark(BookmarkBase):
    id: str
    user_id: str
    created_at: datetime

# 검색 관련 모델
class SearchQuery(BaseModel):
    query: str
    category: Optional[ArticleCategory] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    limit: int = 20

class SearchResult(BaseModel):
    articles: List[Article]
    total_count: int
    query: str

# 대통령 정책
class President(BaseModel):
    title: str
    context: str
    promise_type: str # 약속 유형 (예: "공약", "정책")
    status: str # 약속 상태 (예: "이행 중", "완료", "미이행")
    category: str # 약속 카테고리 (예: "경제", "사회", "정치")
    progress: Optional[str] = None # 진행 상황 (예: "50% 완료")
    last_update: Optional[str] = None # 마지막 업데이트 날짜
    related_links: Optional[List[str]] = None # 관련 링크
    date: str # 약속 날짜
    created_at: str

# 정책
class ParliamentaryActivity(BaseModel):
    title: str # 활동 제목
    context: str # 활동 내용
    type: str # 활동 유형 (예: "회의", "토론", "법안 심사")
    date: str # 활동 날짜
    status: str # 법안 상태 (예: "발의", "가결", "심사 중" "통과")
    proposer: Optional[str] = None # 발의자
    category: str # 법안 카테고리 (예: "경제", "사회", "정치")
    committee: Optional[str] = None # 소관 위원회
    bill_number: Optional[str] = None # 법안 번호
    description: Optional[str] = None # 법안 설명
    related_links: Optional[List[str]] = None # 관련 링크
    created_at: str

# 정치인 발언
class PoliticalStatement(BaseModel):
    speaker: str # 정치인 이름
    party: str # 정당명
    speak_reason : str # 발언 이유
    context: str # 발언 내용
    category: str # 발언 카테고리 (예: "정책", "논란", "선거", "연대")
    type: str # 발언 성격 (예 : 비판, 공약, 해명, 정책제안, 논란 등)
    related_links: Optional[List[str]] = None # 관련 링크
    date: str # 발언 날짜
    created_at: str

# API 응답 모델
class ResponseModel(BaseModel):
    success: bool
    message: str
    data: Optional[Any] = None

class ErrorResponse(BaseModel):
    success: bool = False
    message: str
    error_code: Optional[str] = None

class Pagination(BaseModel):
    limit: int = 20
    offset: int = 0
    total_count: Optional[int] = None