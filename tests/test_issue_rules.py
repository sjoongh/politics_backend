from utils.issue_rules import (
    is_valid_status, to_summary, sort_events, article_public, patchable, SUMMARY_KEYS,
)


def test_is_valid_status():
    assert is_valid_status("진행중") is True
    assert is_valid_status("가결") is True
    assert is_valid_status("없는상태") is False
    assert is_valid_status(None) is False


def test_to_summary_only_summary_keys():
    issue = {"id": "x", "slug": "s", "title": "t", "summary": "su", "status": "진행중",
             "category": "정치", "started_at": "a", "updated_at": "b",
             "events": [1, 2], "article_ids": ["z"], "secret": "no"}
    out = to_summary(issue)
    assert set(out.keys()) == set(SUMMARY_KEYS) | {"issue_type"}   # 유형 라벨 추가
    assert out["issue_type"] == "manual"   # auto_key 없으면 manual
    assert "events" not in out and "secret" not in out and "auto_key" not in out
    assert out["title"] == "t"


def test_sort_events_by_date():
    events = [{"date": "2026-02-01", "headline": "b"}, {"date": "2026-01-01", "headline": "a"}]
    out = sort_events(events)
    assert [e["headline"] for e in out] == ["a", "b"]
    assert sort_events(None) == []


def test_article_public_subset():
    art = {"id": "1", "title": "t", "ai_summary": "s", "source": "src", "source_url": "u",
           "image_url": "i", "category": "정치", "published_at": "p",
           "view_count": 99, "bookmark_count": 3}
    out = article_public(art)
    assert "view_count" not in out and "bookmark_count" not in out
    assert out["ai_summary"] == "s" and out["id"] == "1"


def test_patchable_filters_protected_fields():
    out = patchable({"title": "new", "status": "가결", "id": "hack",
                     "events": [], "article_ids": ["x"], "started_at": "z"})
    assert out == {"title": "new", "status": "가결"}
    assert patchable(None) == {}
