"""기사 본문 크롤링 유틸 (trafilatura 기반, 옵셔널)."""
try:
    import trafilatura
except ImportError:
    trafilatura = None


def fetch_article_text(url: str, min_len: int = 200) -> str:
    if not url or trafilatura is None:
        return ""
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return ""
        text = trafilatura.extract(downloaded, include_comments=False, include_tables=False) or ""
        text = text.strip()
        return text if len(text) >= min_len else ""
    except Exception:
        return ""
