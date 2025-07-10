from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse

async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": exc.detail
        }
    )

async def general_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "message": "서버 내부 오류가 발생했습니다.",
            "detail": str(exc)  # 필요시 로깅용 디버깅 메시지 포함 가능
        }
    )
