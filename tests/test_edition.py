from utils.edition import kst_date, select_top_issues, build_edition


def test_kst_date_iso():
    assert kst_date("2026-11-09T16:30:00Z") == "2026-11-10"
    assert kst_date("2026-11-09T14:30:00+00:00") == "2026-11-09"


def test_kst_date_plain():
    assert kst_date("2026-11-10") == "2026-11-10"
    assert kst_date("2026-11-10 01:02:03") == "2026-11-10"   # naive → UTC로 간주


def test_kst_date_bad():
    assert kst_date("") is None and kst_date(None) is None and kst_date("nope") is None


def test_top_issues_by_rank_same_day():
    iss = [{"id": "a", "title": "A", "active": True, "digest": {"rank": 5, "last_activity_at": "2026-11-10T01:00:00+00:00", "counts": {}, "stance": [{"basis": "press"}]}},
           {"id": "b", "title": "B", "active": True, "digest": {"rank": 9, "last_activity_at": "2026-11-10T02:00:00+00:00", "counts": {}, "stance": []}},
           {"id": "c", "title": "C", "active": True, "digest": {"rank": 99, "last_activity_at": "2026-11-01T02:00:00+00:00", "counts": {}}},
           {"id": "d", "title": "D", "active": False, "digest": {"rank": 50, "last_activity_at": "2026-11-10T02:00:00+00:00", "counts": {}}}]
    top = select_top_issues(iss, "2026-11-10")
    assert [t["id"] for t in top] == ["b", "a"]
    assert top[1]["stance"] == []            # press 입장은 판에 넣지 않는다
    assert set(top[0]) >= {"id", "title", "summary", "status", "category", "counts", "vote", "stance"}


def test_build_edition_sections():
    src = [{"id": "v", "type": "assembly_vote", "published_at": "2026-11-10", "title": "표결: X", "law_name": "X",
            "procedural": False, "issue_ids": [], "vote": {"yes": 1, "no": 0, "abstain": 0, "result": "가결"}},
           {"id": "b", "type": "assembly_bill", "published_at": "2026-11-10", "title": "Y 개정안", "law_name": "Y", "issue_ids": ["i1"]},
           {"id": "g", "type": "gov_policy", "published_at": "2026-11-10T03:00:00Z", "title": "브리핑", "issue_ids": []},
           {"id": "old", "type": "gov_policy", "published_at": "2026-11-01T03:00:00Z", "title": "x", "issue_ids": []}]
    e = build_edition("2026-11-10", [], src, None)
    assert len(e["assembly"]["votes"]) == 1 and len(e["assembly"]["bills"]) == 1 and len(e["government"]) == 1
    assert e["overview"] is None and e["date"] == "2026-11-10" and e["built_at"]
    assert e["assembly"]["votes"][0]["vote"]["yes"] == 1 and e["assembly"]["bills"][0]["issue_ids"] == ["i1"]


def test_build_edition_other_issue_ids_excludes_top():
    iss = [{"id": f"i{n}", "title": "t", "active": True, "digest": {"rank": n, "last_activity_at": "2026-11-10T01:00:00+00:00", "counts": {}}} for n in range(1, 6)]
    e = build_edition("2026-11-10", iss, [], "요약")
    assert [t["id"] for t in e["top_issues"]] == ["i5", "i4", "i3"] and e["other_issue_ids"] == ["i2", "i1"]
    assert e["overview"] == "요약"
