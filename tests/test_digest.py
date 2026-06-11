from utils.digest import matches_interests


def test_match_in_title():
    a = {"title": "대통령 거부권 행사", "keywords": []}
    assert matches_interests(a, ["거부권"]) is True


def test_match_in_keywords():
    a = {"title": "본회의 통과", "keywords": ["예산", "추경"]}
    assert matches_interests(a, ["추경"]) is True


def test_no_match():
    a = {"title": "날씨 맑음", "keywords": ["기상"]}
    assert matches_interests(a, ["국회"]) is False


def test_empty_interests_false():
    assert matches_interests({"title": "x", "keywords": []}, []) is False
    assert matches_interests({"title": "x"}, ["  "]) is False


def test_case_insensitive():
    assert matches_interests({"title": "AI 정책", "keywords": []}, ["ai"]) is True
