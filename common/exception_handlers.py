import traceback

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


class UnhandledErrorMiddleware:
    """미처리 예외를 CORS 안쪽에서 500 JSON으로 바꾼다.
    Starlette의 Exception 핸들러는 CORS 바깥(ServerErrorMiddleware)에서 돌아 CORS 헤더가 빠지고,
    브라우저는 500 대신 CORS 오류만 보게 된다."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        started = False

        async def _send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, _send)
        except Exception as exc:
            if started:
                raise
            # 다시 올리지 않는다(응답을 보낸 뒤의 예외 처리는 서버마다 달라 Vercel에서 보장되지 않음). 로깅·Sentry는 여기서.
            traceback.print_exc()
            _capture(exc)
            handler = scope["app"].exception_handlers.get(Exception, general_exception_handler)
            response = await handler(Request(scope), exc)
            await response(scope, receive, send)


def _capture(exc: Exception):
    try:
        import sentry_sdk
        sentry_sdk.capture_exception(exc)
    except Exception:
        pass


def configure_errors_and_cors(app):
    """오류 처리와 CORS 설정. 나중에 추가한 미들웨어가 바깥이므로 CORS를 마지막에 둔다."""
    from fastapi.middleware.cors import CORSMiddleware
    from starlette.exceptions import HTTPException as StarletteHTTPException

    app.add_middleware(UnhandledErrorMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 모든 오리진 허용(웹/모바일). 자격증명 미사용이라 와일드카드 유효.
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)
