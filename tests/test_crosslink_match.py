from utils.crosslink_match import article_matches_issue

NEWS = {"auto_key": "news:1", "keywords": ["멱살 파문", "권영진"], "title": "권영진 ‘멱살 파문’",
        "entities": {"people": ["권영진"]}}


def test_name_only_not_enough():
    assert not article_matches_issue("권영진 의원 지역구 행사 참석", NEWS)


def test_phrase_full_match():
    assert article_matches_issue("국민의힘 멱살 파문 징계 착수", NEWS)


def test_two_tokens_match():
    assert article_matches_issue("멱살 잡은 파문 확산", NEWS)


def test_one_token_plus_name_not_enough():
    assert not article_matches_issue("권영진 멱살 잡아", NEWS)   # 토큰 1개(멱살)+인명 → 부족
    assert not article_matches_issue("파문 확산 중", NEWS)


def test_bill_issue_uses_law_name():
    assert article_matches_issue("국민연금법 개정안 통과", {"auto_key": "bill:1", "law_name": "국민연금법", "keywords": ["국민연금법"]})


def test_manual_issue_uses_keywords_3plus():
    assert article_matches_issue("추가경정예산안 심사 돌입", {"keywords": ["추가경정예산안", "예산"]})
    assert not article_matches_issue("예산 논의", {"keywords": ["추가경정예산안", "예산"]})


def test_prune_mode_keeps_single_token_but_not_name_only():
    assert article_matches_issue("권영진 멱살 잡아", NEWS, min_tokens=1)
    assert not article_matches_issue("권영진 의원 지역구 행사 참석", NEWS, min_tokens=1)
