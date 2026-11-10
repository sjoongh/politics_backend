from utils.fallback_summary import fallback_summary


def test_news_prefers_center_latest():
    iss = {"auto_key": "news:1", "title": "t",
           "article_meta": {"a": {"leaning": "left", "at": "2026-11-10"}, "b": {"leaning": "center", "at": "2026-11-09"}}}
    arts = {"a": {"title": "한겨레 제목"}, "b": {"title": "연합 제목"}}
    assert fallback_summary(iss, arts) == "연합 제목"


def test_news_without_center_uses_latest():
    iss = {"auto_key": "news:1", "title": "t",
           "article_meta": {"a": {"leaning": "left", "at": "2026-11-10"}, "b": {"leaning": "right", "at": "2026-11-09"}}}
    assert fallback_summary(iss, {"a": {"title": "A"}, "b": {"title": "B"}}) == "A"


def test_bill_format():
    assert fallback_summary({"auto_key": "bill:1", "law_name": "국민연금법", "status": "가결",
                             "updated_at": "2026-11-08"}, {}) == "국민연금법 · 가결 · 11.8"


def test_never_empty():
    assert fallback_summary({"auto_key": "news:1", "title": "제목만"}, {}) == "제목만"
