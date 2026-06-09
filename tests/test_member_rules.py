from utils.member_rules import confirmed_records, has_missing_source, criminal_count, MEMBER_DISCLAIMER


def _recs():
    return [
        {"offense": "a", "disposition": "벌금", "is_final": True, "source_url": "http://s/1"},
        {"offense": "b", "disposition": "수사중", "is_final": False, "source_url": "http://s/2"},
    ]


def test_confirmed_records_filters_non_final():
    out = confirmed_records(_recs())
    assert len(out) == 1
    assert out[0]["offense"] == "a"
    assert confirmed_records([]) == []
    assert confirmed_records(None) == []


def test_criminal_count_counts_only_final():
    assert criminal_count(_recs()) == 1
    assert criminal_count(None) == 0


def test_has_missing_source_detects_empty_or_absent():
    assert has_missing_source([{"offense": "a", "source_url": ""}]) is True
    assert has_missing_source([{"offense": "a"}]) is True
    assert has_missing_source([{"offense": "a", "source_url": "  "}]) is True
    assert has_missing_source([{"offense": "a", "source_url": "http://s/1"}]) is False
    assert has_missing_source([]) is False


def test_disclaimer_mentions_official_and_final():
    assert "선거관리위원회" in MEMBER_DISCLAIMER
    assert "확정" in MEMBER_DISCLAIMER
