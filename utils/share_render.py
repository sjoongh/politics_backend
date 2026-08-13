"""공유용 OG 카드 HTML을 만드는 순수 함수. Firestore/FastAPI 비의존."""
import html
import json

TITLE_MAX = 60
DESC_MAX = 150
DEFAULT_TITLE = "브리핑 코리아 · 정치 브리핑"
DEFAULT_DESC = "실시간 정치 뉴스와 1차 소스 맥락 — 브리핑 코리아"


def _clip(s: str, n: int) -> str:
    s = (s or "").strip()
    if len(s) <= n:
        return s
    return s[: n - 1].rstrip() + "…"


def _js_string(s: str) -> str:
    # <script> 안에서 안전한 JS 문자열 리터럴. </script> 및 < 차단.
    return json.dumps(s or "").replace("<", "\\u003c")


def render_share_html(*, title, description, image_url, share_url, redirect_url) -> str:
    t = html.escape(_clip(title, TITLE_MAX) or DEFAULT_TITLE)
    d = html.escape(_clip(description, DESC_MAX) or DEFAULT_DESC)
    img = html.escape(image_url or "")
    su = html.escape(share_url or "")
    ru_attr = html.escape(redirect_url or "")
    ru_js = _js_string(redirect_url)
    return (
        "<!DOCTYPE html><html lang=\"ko\"><head>"
        "<meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<meta property=\"og:type\" content=\"article\">"
        f"<meta property=\"og:title\" content=\"{t}\">"
        f"<meta property=\"og:description\" content=\"{d}\">"
        f"<meta property=\"og:image\" content=\"{img}\">"
        f"<meta property=\"og:url\" content=\"{su}\">"
        "<meta name=\"twitter:card\" content=\"summary_large_image\">"
        f"<meta name=\"twitter:title\" content=\"{t}\">"
        f"<meta name=\"twitter:description\" content=\"{d}\">"
        f"<meta name=\"twitter:image\" content=\"{img}\">"
        f"<title>{t}</title>"
        f"<script>location.replace({ru_js});</script>"
        "</head><body>"
        f"<noscript><a href=\"{ru_attr}\">브리핑 코리아에서 보기</a></noscript>"
        "</body></html>"
    )
