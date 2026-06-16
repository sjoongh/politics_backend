from utils.law_name import normalize_law_name, is_procedural


def test_normalize_strips_procedural_terms():
    assert normalize_law_name("항공안전법 일부개정법률안(대안)(국토교통위원장)") == "항공안전법"
    assert normalize_law_name("국민연금법 전부개정법률안") == "국민연금법"
    assert normalize_law_name("표결: 철도안전법 일부개정법률안(대안)") == "철도안전법"


def test_is_procedural():
    assert is_procedural("항공안전법 일부개정법률안(대안)(국토교통위원장)") is True
    assert is_procedural("기후위기 특별위원회 구성의 건(의장)") is True
    assert is_procedural("노란봉투법") is False
