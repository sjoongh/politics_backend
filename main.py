import datetime
from dotenv import load_dotenv
from fastapi import FastAPI
from routers import auth_router, bookmark_router, comment_router, feedback_router, news_router, notification_router, politics_router, statistic_router, summary_router, health_check_router, member_router, issue_router, assembly_router, source_router, share_router
import os
from common.exception_handlers import configure_errors_and_cors

# 환경 변수 로드
load_dotenv()

# 관측성: SENTRY_DSN 설정 시에만 에러 모니터링 활성(미설정·미설치면 no-op)
if os.getenv("SENTRY_DSN"):
    try:
        import sentry_sdk
        sentry_sdk.init(dsn=os.getenv("SENTRY_DSN"),
                        traces_sample_rate=float(os.getenv("SENTRY_TRACES_RATE", "0.0")),
                        environment=os.getenv("VERCEL_ENV", "production"))
    except Exception as _e:  # 설치 안 됨 등 — 모니터링 없이 계속
        print(f"[sentry] init skipped: {_e!r}")

# FastAPI 앱 생성
app = FastAPI(
    title="정치 뉴스 추적 API",
    description="Firebase + Python + AI를 활용한 정치 뉴스 수집 및 요약 서비스",
    version="1.0.0"
)

configure_errors_and_cors(app)

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
from routers import today_router
app.include_router(today_router.router, prefix="/api/today")
app.include_router(assembly_router.router, prefix="/api/assembly")
app.include_router(source_router.router, prefix="/api/sources")
app.include_router(statistic_router.router, prefix="/api/statistic")
app.include_router(summary_router.router, prefix="/api/summaries")
app.include_router(health_check_router.router, prefix="/healthz") # 헬스 체크용 라우터 추가
app.include_router(share_router.router)