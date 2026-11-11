"""공개 읽기 API 캐시 헤더. 성공은 CDN 5분+재검증 1시간, 오류는 캐시 금지."""
OK = "public, s-maxage=300, stale-while-revalidate=3600"
ERR = "no-store"


def cache_headers(ok: bool) -> dict:
    return {"Cache-Control": OK if ok else ERR}
