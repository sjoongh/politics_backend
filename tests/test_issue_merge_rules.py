from utils.issue_merge_rules import follow_merge


def test_follow_single_hop():
    docs = {"a": {"merged_into": "b"}, "b": {}}
    assert follow_merge("a", docs.get) == "b"


def test_follow_stops_on_cycle():
    docs = {"a": {"merged_into": "b"}, "b": {"merged_into": "a"}}
    assert follow_merge("a", docs.get) in ("a", "b")  # 종료가 핵심


def test_follow_missing_returns_input():
    assert follow_merge("zzz", lambda _id: None) == "zzz"


def test_follow_max_hops():
    docs = {"a": {"merged_into": "b"}, "b": {"merged_into": "c"}, "c": {"merged_into": "d"},
            "d": {"merged_into": "e"}, "e": {}}
    assert follow_merge("a", docs.get, max_hops=3) == "d"
