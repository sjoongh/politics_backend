from datetime import datetime, timezone
from utils.issue_digest import (count_sources, representative_vote, stance_from_vote, stance_from_official,
                                bias_from_meta, rank_score, build_digest)
from utils.ministries import ministry_of

NOW = datetime(2026, 11, 10, tzinfo=timezone.utc)
VOTE = {"id": "v1", "type": "assembly_vote", "title": "표결: 국민연금법", "published_at": "2026-11-08",
        "vote": {"yes": 193, "no": 40, "abstain": 6, "result": "가결",
                 "party_breakdown": {"더불어민주당": {"yes": 160, "no": 0, "abstain": 1},
                                     "무소속": {"yes": 0, "no": 0, "abstain": 0}}}}


def test_counts():
    assert count_sources([VOTE, {"type": "gov_policy"}]) == {"gov": 1, "bill": 0, "vote": 1}


def test_rep_vote_latest():
    older = {**VOTE, "id": "v0", "published_at": "2026-01-01"}
    rv = representative_vote([older, VOTE])
    assert rv["source_id"] == "v1" and rv["yes"] == 193 and rv["bill_name"] == "국민연금법" and rv["date"] == "2026-11-08"


def test_rep_vote_none_without_votes():
    assert representative_vote([{"type": "gov_policy"}]) is None


def test_vote_stance_skips_empty_party():
    rows = stance_from_vote(VOTE)
    assert [r["actor"] for r in rows] == ["더불어민주당"]
    assert rows[0]["basis"] == "vote" and rows[0]["position"] == {"yes": 160, "no": 0, "abstain": 1}
    assert rows[0]["source_id"] == "v1"


def test_official_requires_position():
    assert stance_from_official([{"id": "g", "type": "gov_policy", "title": "기획재정부, 추경 집행", "position": None}]) == []


def test_official_actor_is_ministry_latest_per_actor():
    rows = stance_from_official([
        {"id": "g1", "type": "gov_policy", "title": "기획재정부, 추경 집행", "position": "explain",
         "claim_summary": "2주 내 집행", "url": "u1", "published_at": "2026-11-10T00:00:00Z"},
        {"id": "g0", "type": "gov_policy", "title": "기획재정부 브리핑", "position": "propose",
         "claim_summary": "이전", "url": "u0", "published_at": "2026-10-01T00:00:00Z"},
    ])
    assert len(rows) == 1 and rows[0]["actor"] == "기획재정부" and rows[0]["evidence"] == "2주 내 집행"
    assert rows[0]["basis"] == "official" and rows[0]["source_id"] == "g1"


def test_ministry():
    assert ministry_of("기획재정부는 오늘") == "기획재정부"
    assert ministry_of("아무 말") == "정부"
    assert ministry_of("보건복지부와 기획재정부") == "보건복지부"


def test_bias_merges_official_into_unknown():
    assert bias_from_meta({"a": {"leaning": "official"}, "b": {"leaning": "left"}}) == \
        {"left": 1, "center": 0, "right": 0, "foreign": 0, "unknown": 1}


def test_rank_caps_and_decays():
    fresh = rank_score({"auto_generated": True, "newsworthiness": 99}, {"gov": 1, "bill": 1, "vote": 1},
                       "2026-11-10T00:00:00+00:00", NOW)
    old = rank_score({"auto_generated": True, "newsworthiness": 99}, {"gov": 1, "bill": 1, "vote": 1},
                     "2026-11-01T00:00:00+00:00", NOW)
    assert fresh <= 40 and old < fresh
    assert rank_score({"auto_generated": False}, {"gov": 0, "bill": 0, "vote": 0},
                      "2026-11-10T00:00:00+00:00", NOW) >= 1000


def test_rank_handles_bad_timestamp():
    assert rank_score({"auto_generated": True, "newsworthiness": 5}, {"gov": 0, "bill": 0, "vote": 0}, "", NOW) >= 0


def test_build_digest_shape():
    d = build_digest({"auto_generated": True, "newsworthiness": 5,
                      "article_meta": {"a": {"leaning": "left", "at": "2026-11-09T00:00:00+00:00"}}}, [VOTE], NOW)
    assert d["counts"] == {"gov": 0, "bill": 0, "vote": 1, "media": 1}
    assert d["has_vote"] and d["has_official"] and not d["has_gov"]
    assert d["vote"]["yes"] == 193 and d["stance"][0]["basis"] == "vote"
    assert d["bias"]["left"] == 1 and d["last_activity_at"] == "2026-11-09T00:00:00+00:00"
    assert "rank" in d and d["rank_at"]


def test_build_digest_press_appended_and_capped():
    press = [{"actor": f"a{i}", "position": "neutral", "basis": "press"} for i in range(6)]
    d = build_digest({"auto_generated": True, "article_meta": {}}, [VOTE], NOW, press_stance=press)
    assert len(d["stance"]) == 6 and d["stance"][0]["basis"] == "vote"
