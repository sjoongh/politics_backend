from utils.issue_list_query import build_query_plan, SORT_FIELDS


def test_default_plan():
    assert build_query_plan(None, None) == {"order": "digest.rank", "where": [("active", "==", True)]}


def test_filter_vote():
    plan = build_query_plan("updated", "has_vote")
    assert ("digest.has_vote", "==", True) in plan["where"] and plan["order"] == "digest.last_activity_at"


def test_unknown_sort_falls_back():
    assert build_query_plan("zzz", None)["order"] == "digest.rank"


def test_status_filter():
    assert ("status", "==", "가결") in build_query_plan(None, "status:가결")["where"]


def test_unknown_filter_ignored():
    assert build_query_plan("media", "bogus") == {"order": "digest.counts.media", "where": [("active", "==", True)]}


def test_sort_fields_cover_three():
    assert set(SORT_FIELDS) == {"rank", "updated", "media"}
