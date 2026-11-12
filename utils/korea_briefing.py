"""정책브리핑 보도자료 목록 페이지 파서 (firebase 비의존, 테스트 대상).

korea.kr RSS는 2026-07-01 제공 중단(공지 noticeView.do?newsId=132038885). robots.txt가 허용하는
보도자료 목록 1페이지에서 제목·부처·날짜·원문 링크와 짧은 발췌만 읽는다. 본문 페이지는 열지 않는다.
"""
import html
import re

PRESS_LIST_URL = "https://www.korea.kr/briefing/pressReleaseList.do"
_VIEW = "https://www.korea.kr/briefing/pressReleaseView.do?newsId="

_ITEM = re.compile(
    r'<a href="/briefing/pressReleaseView\.do\?newsId=(\d+)[^"]*">\s*'
    r'<span class="text">\s*<strong>(.*?)</strong>\s*'
    r'<span class="lead">(.*?)</span>\s*'
    r'<span class="source">\s*<span>(\d{4})\.(\d{2})\.(\d{2})</span>\s*<span>(.*?)</span>',
    re.S)
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def _text(s: str) -> str:
    return _WS.sub(" ", html.unescape(_TAG.sub("", s or ""))).strip()


def parse_press_list(page: str) -> list[dict]:
    """목록 HTML → normalize_gov_policy 입력 dict 목록. 구조가 바뀌면 빈 목록."""
    out = []
    for m in _ITEM.finditer(page or ""):
        news_id, title, lead, y, mo, d, ministry = m.groups()
        title = _text(title)
        if not title:
            continue
        out.append({"title": title, "link": _VIEW + news_id, "description": _text(lead),
                    "date": f"{y}-{mo}-{d}", "ministry": _text(ministry) or None})
    return out
