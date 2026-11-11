from utils.http_cache import cache_headers


def test_ok_is_public_cached():
    h = cache_headers(True)
    assert h["Cache-Control"] == "public, s-maxage=300, stale-while-revalidate=3600, stale-if-error=86400"


def test_error_is_no_store():
    assert cache_headers(False) == {"Cache-Control": "no-store"}
