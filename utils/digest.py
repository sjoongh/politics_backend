"""개인화 관심 매칭 순수 로직 (firebase 비의존, 테스트 대상)."""


def matches_interests(article, interests) -> bool:
    """기사 제목/키워드에 관심 키워드가 하나라도 포함되면 True."""
    terms = [i.strip().lower() for i in (interests or []) if i and i.strip()]
    if not terms:
        return False
    hay = (article.get("title", "") + " " + " ".join(article.get("keywords") or [])).lower()
    return any(t in hay for t in terms)
