from utils.law_name import normalize_law_name, is_procedural


def test_normalize_strips_procedural_terms():
    assert normalize_law_name("항공안전법 일부개정법률안(대안)(국토교통위원장)") == "항공안전법"
    assert normalize_law_name("국민연금법 전부개정법률안") == "국민연금법"
    assert normalize_law_name("표결: 철도안전법 일부개정법률안(대안)") == "철도안전법"


def test_is_procedural():
    # 위원회 대안 법률안은 실질 법률(절차안 아님)
    assert is_procedural("항공안전법 일부개정법률안(대안)(국토교통위원장)") is False
    assert is_procedural("항만법 일부개정법률안(대안)(농림축산식품해양수산위원장)") is False
    assert is_procedural("기후위기 특별위원회 구성의 건(의장)") is True
    assert is_procedural("제437회국회(임시회) 회기결정의 건(국회운영위원장)") is True
    assert is_procedural("지방주도성장을 위한 초광역권전략산업특구 특별위원회 구성결의안(국회운영위원장)") is True
    assert is_procedural("노란봉투법") is False
