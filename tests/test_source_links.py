from utils.source_links import add_link, has_link, is_rejected, news_issue_link_score, issue_ids_of


def test_add_link_updates_mirrors():
    s = add_link({"id": "s"}, "i1", "auto", 12.0, "law_name", "2026-11-10")
    assert s["issue_ids"] == ["i1"] and s["issue_id"] == "i1" and s["link_status"] == "auto"
    assert s["links"][0]["reason"] == "law_name" and has_link(s, "i1")


def test_rejected_not_in_issue_ids():
    s = add_link({"id": "s"}, "i1", "rejected", 0, "manual", "t")
    assert s["issue_ids"] == [] and is_rejected(s, "i1") and s["link_status"] == "rejected"


def test_replace_same_issue_and_keep_rejected():
    s = add_link({"id": "s"}, "i1", "pending", 5.0, "proposer", "t1")
    s = add_link(s, "i1", "confirmed", 5.0, "review", "t2")
    s = add_link(s, "i2", "rejected", 0, "review", "t3")
    s = add_link(s, "i2", "auto", 12.0, "law_name", "t4")   # 거절된 관계는 자동으로 되살리지 않는다
    assert issue_ids_of(s) == ["i1"] and len(s["links"]) == 2 and is_rejected(s, "i2")


def test_mirror_prefers_first_approved_link():
    s = add_link({"id": "s"}, "i1", "pending", 5.0, "x", "t")
    s = add_link(s, "i2", "auto", 12.0, "y", "t")
    assert s["issue_id"] == "i2" and s["link_status"] == "auto"


def test_score_exact_law_name():
    assert news_issue_link_score({"law_name": "국민연금법", "bill": {"bill_name": "국민연금법 일부개정법률안", "proposers": []}},
                                 "국민연금법 개정 논란", []) == (12.0, "auto")


def test_score_proposer_pending():
    assert news_issue_link_score({"law_name": "xx", "bill": {"bill_name": "yy", "proposers": ["김승원"]}}, "무관", ["김승원"]) == (5.0, "pending")


def test_score_short_law_name_ignored():
    assert news_issue_link_score({"law_name": "형법", "bill": None}, "형법 개정", []) == (0, None)
