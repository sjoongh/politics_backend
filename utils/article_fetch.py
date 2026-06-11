"""기사 본문 크롤링 유틸 (trafilatura 기반)."""
import trafilatura


def fetch_article_text(url: str, min_len: int = 200) -> str:
    """기사 URL에서 본문 텍스트를 추출. 실패하거나 너무 짧으면 빈 문자열 반환.
    (네트워크 호출이므로 async 컨텍스트에서는 asyncio.to_thread로 감쌀 것)
    """
    if not url:
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
