from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse

async def http_exception_handler(request: Request, exc: HTTPException):
    # 오류 응답은 캐시 금지(no-store)가 기본. 라우터가 지정한 헤더(예: Cache-Control)는 보존한다.
    headers = {"Cache-Control": "no-store"}
    headers.update(getattr(exc, "headers", None) or {})
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": exc.detail
        },
        headers=headers,
    )

async def general_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "message": "서버 내부 오류가 발생했습니다.",
            "detail": str(exc)  # 필요시 로깅용 디버깅 메시지 포함 가능
        },
        headers={"Cache-Control": "no-store"},
    )
