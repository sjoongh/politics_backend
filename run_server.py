import uvicorn
import os
from dotenv import load_dotenv
import logging

# 환경 변수 로드
load_dotenv()

logging.basicConfig(level=logging.DEBUG)

if __name__ == "__main__":
    # 개발 환경 설정
    debug_mode = os.getenv("DEBUG", "True").lower() == "true"
    port = int(os.getenv("PORT", "8000"))

    print("🚀 정치 뉴스 추적 API 서버를 시작합니다...")
    print(f"📍 서버 주소: http://localhost:{port}")
    print(f"📖 API 문서: http://localhost:{port}/docs")
    print(f"🔧 디버그 모드: {debug_mode}")

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=debug_mode,
        access_log=True,
        log_level="info"
    )