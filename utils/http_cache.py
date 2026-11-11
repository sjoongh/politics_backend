"""공개 읽기 API 캐시 헤더.
성공: CDN 5분 + 재검증 1시간 + 원본 오류 시 24시간 stale 응답(Firestore 429로 500이 나도 마지막 정상본 제공).
오류: 캐시 금지. 개인화 응답: CDN·공유 캐시 금지."""
OK = "public, s-maxage=300, stale-while-revalidate=3600, stale-if-error=86400"
ERR = "no-store"
PRIVATE = "private, no-store"


def cache_headers(ok: bool) -> dict:
    return {"Cache-Control": OK if ok else ERR}


def private_headers() -> dict:
    return {"Cache-Control": PRIVATE}
