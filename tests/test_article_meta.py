from utils.article_meta import meta_for, merge_meta, sorted_article_ids


def test_meta_for_uses_leaning():
    m = meta_for({"id": "a", "source": "한겨레", "created_at": "2026-11-10T01:00:00+00:00"})
    assert m == {"source": "한겨레", "leaning": "left", "at": "2026-11-10T01:00:00+00:00"}


def test_meta_for_datetime_created_at_and_fallback():
    from datetime import datetime, timezone
    m = meta_for({"id": "a", "source": "연합뉴스", "created_at": datetime(2026, 11, 10, tzinfo=timezone.utc)})
    assert m["at"].startswith("2026-11-10")
    assert meta_for({"id": "b", "source": "x", "published_at": "2026-01-02 03:04:05"})["at"] == "2026-01-02 03:04:05"


def test_merge_keeps_existing():
    out = merge_meta({"a": {"source": "x", "leaning": "unknown", "at": "2026-01-01"}},
                     [{"id": "b", "source": "연합뉴스", "created_at": "2026-02-01"}])
    assert set(out) == {"a", "b"} and out["a"]["source"] == "x"


def test_sorted_desc():
    meta = {"a": {"at": "2026-01-01"}, "b": {"at": "2026-03-01"}, "c": {}}
    assert sorted_article_ids(meta) == ["b", "a", "c"]


def test_attach_articles_preserves_unknown_ids_at_tail():
    from utils.article_meta import attach_articles
    issue = {"article_ids": ["old1"], "article_meta": {}}
    patch = attach_articles(issue, [{"id": "n1", "source": "연합뉴스", "created_at": "2026-11-10"}])
    assert patch["article_ids"] == ["n1", "old1"] and "n1" in patch["article_meta"]
