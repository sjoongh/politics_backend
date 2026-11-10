"""이슈 ↔ 기사 크로스링크 매칭 규칙(순수).

뉴스 이슈: 인명 단독 일치로는 붙이지 않는다(라이브에서 한 인물 이슈에 기사 160건이 붙던 원인).
  대표 인용구 전체 포함 OR 인용구 토큰(2자↑, 불용어 제외) 2개 이상 포함.
법안·수동 이슈: law_name 또는 키워드(3자↑) 포함(기존 규칙).
"""
import re

_STOP = {"관련", "논란", "현안", "의원", "대표", "정부", "국회", "오늘", "내일", "이번", "지난", "대해", "위해"}


def _is_news(issue: dict) -> bool:
    return str(issue.get("auto_key") or "").startswith("news:")


def _people(issue: dict) -> set:
    return set((issue.get("entities") or {}).get("people") or [])


def phrase_tokens(phrase: str) -> list:
    out = []
    for t in re.split(r"[\s,·‘’'\"…]+", phrase or ""):
        t = t.strip()
        if len(t) >= 2 and t not in _STOP:
            out.append(t)
    return out


def news_phrases(issue: dict) -> list:
    people = _people(issue)
    return [k for k in (issue.get("keywords") or []) if k and k not in people]


def article_matches_issue(blob: str, issue: dict, min_tokens: int = 2) -> bool:
    """min_tokens=2: 신규 연결(정밀도 우선). min_tokens=1: 기존 연결 정리(인명 단독만 제거)."""
    blob = blob or ""
    if _is_news(issue):
        for phrase in news_phrases(issue):
            if len(phrase) >= 4 and phrase in blob:
                return True
            toks = [t for t in phrase_tokens(phrase) if t not in _people(issue)]
            need = min(min_tokens, len(toks)) if toks else 0
            if need and sum(1 for t in toks if t in blob) >= need:
                return True
        return False
    terms = set()
    if issue.get("law_name") and len(issue["law_name"]) >= 3:
        terms.add(issue["law_name"])
    for k in (issue.get("keywords") or []):
        if k and len(k) >= 3:
            terms.add(k)
    return any(t in blob for t in terms)
