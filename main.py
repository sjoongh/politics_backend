import datetime
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import auth_router, bookmark_router, comment_router, feedback_router, news_router, notification_router, politics_router, statistic_router, summary_router, health_check_router, member_router, issue_router
import os
from common.exception_handlers import http_exception_handler, general_exception_handler  # 위에서 만든 함수들
from starlette.exceptions import HTTPException as StarletteHTTPException

# 환경 변수 로드
load_dotenv()

# FastAPI 앱 생성
app = FastAPI(
    title="정치 뉴스 추적 API",
    description="Firebase + Python + AI를 활용한 정치 뉴스 수집 및 요약 서비스",
    version="1.0.0"
)

# allow_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
# allow_origins.append("https://koreanpolitical.web.app")
# allow_origins.append("https://koreanpolitical.firebaseapp.com")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 기존에 로드한 것과 추가된 도메인 포함
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)

# 루트 경로
@app.get("/")
async def root():
    return {"message": "정치 뉴스 추적 API 서버가 실행 중입니다.", "version": "1.0.0"}

# 헬스 체크
@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.datetime.utcnow().isoformat()}

# 라우터 등록
app.include_router(auth_router.router, prefix="/api/auth")
app.include_router(bookmark_router.router, prefix="/api/bookmarks")
app.include_router(comment_router.router, prefix="/api/comments")
app.include_router(feedback_router.router, prefix="/api/feedback")
app.include_router(news_router.router, prefix="/api/news")
app.include_router(notification_router.router, prefix="/api/notifications")
app.include_router(politics_router.router, prefix="/api/politics")
app.include_router(member_router.router, prefix="/api/members")
app.include_router(issue_router.router, prefix="/api/issues")
app.include_router(statistic_router.router, prefix="/api/statistic")
app.include_router(summary_router.router, prefix="/api/summaries")
app.include_router(health_check_router.router, prefix="/healthz") # 헬스 체크용 라우터 추가