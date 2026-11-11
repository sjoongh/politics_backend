from utils.gemini_rest import parse_stances

SN = ["민주당 “추경 즉시 처리” — ...", "국민의힘 “현금 살포” 비판 — ..."]


def test_parse_filters_bad_position():
    out = parse_stances([{"actor": "민주당", "position": "support", "evidence": "즉시 처리", "article_index": 0},
                         {"actor": "x", "position": "meh", "evidence": "", "article_index": 1}], SN)
    assert len(out) == 1 and out[0]["basis"] == "press" and out[0]["actor"] == "민주당"
    assert out[0]["evidence"] == "즉시 처리" and out[0]["evidence_title"].startswith("민주당")


def test_parse_caps_four():
    rows = [{"actor": f"a{i}", "position": "neutral", "evidence": "e", "article_index": 0} for i in range(6)]
    assert len(parse_stances(rows, SN)) == 4


def test_parse_non_list_is_empty():
    assert parse_stances({"actor": "x"}, SN) == [] and parse_stances(None, SN) == []
