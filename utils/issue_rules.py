"""이슈 추적 순수 로직 (firebase 비의존, 테스트 대상)."""

VALID_STATUS = {"진행중", "계류", "가결", "부결", "종결", "소강"}
SUMMARY_KEYS = ("id", "slug", "title", "summary", "status", "category", "started_at", "updated_at",
                "auto_generated", "auto_key", "newsworthiness")
PATCHABLE_FIELDS = {"title", "summary", "status", "category", "slug", "keywords", "official_links"}
ARTICLE_PUBLIC_KEYS = ("id", "title", "ai_summary", "source", "source_url", "image_url", "category", "published_at")


def is_valid_status(status) -> bool:
    return status in VALID_STATUS


def to_summary(issue: dict) -> dict:
    """목록용 요약 필드만 추출."""
    return {k: issue.get(k) for k in SUMMARY_KEYS}


def sort_events(events):
    """이벤트를 날짜 오름차순 정렬."""
    return sorted(events or [], key=lambda e: e.get("date", ""))


def article_public(article: dict) -> dict:
    """기사에서 공개 필드만 추출."""
    return {k: article.get(k) for k in ARTICLE_PUBLIC_KEYS}


def patchable(fields: dict) -> dict:
    """PATCH로 덮어쓸 수 있는 필드만 허용(id/events/article_ids/timestamps 보호)."""
    return {k: v for k, v in (fields or {}).items() if k in PATCHABLE_FIELDS}
