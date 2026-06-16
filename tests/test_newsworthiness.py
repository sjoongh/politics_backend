from utils.newsworthiness import vote_contention, issue_score, PROMOTE


def test_contention_unanimous_is_zero():
    v = {"yes": 5, "no": 0, "abstain": 0, "party_breakdown": {"A": {"yes": 5, "no": 0, "abstain": 0}}}
    assert vote_contention(v) == 0.0


def test_contention_cross_party_opposition_high():
    v = {"yes": 5, "no": 4, "abstain": 0,
         "party_breakdown": {"여당": {"yes": 5, "no": 0}, "야당": {"yes": 0, "no": 4}}}
    assert vote_contention(v) >= 0.5


def test_score_procedural_demoted_below_hot():
    proc = issue_score(
        {"procedural": True},
        source_items=[{"type": "assembly_bill"},
                      {"type": "assembly_vote",
                       "vote": {"yes": 3, "no": 0, "party_breakdown": {"A": {"yes": 3, "no": 0}}}}],
        article_count=0)
    hot = issue_score(
        {"procedural": False},
        source_items=[{"type": "assembly_vote",
                       "vote": {"yes": 5, "no": 4,
                                "party_breakdown": {"여": {"yes": 5, "no": 0}, "야": {"yes": 0, "no": 4}}}},
                      {"type": "gov_policy"}],
        article_count=4)
    assert hot > proc
    assert proc < PROMOTE   # 절차안 + 무뉴스 + 만장일치 → 승격 미달
