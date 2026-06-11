from utils.source_bias import source_leaning, bias_breakdown


def test_source_leaning_known():
    assert source_leaning("한겨레") == "left"
    assert source_leaning("동아일보") == "right"
    assert source_leaning("연합뉴스") == "center"
    assert source_leaning("BBC 코리아") == "foreign"
    assert source_leaning("대통령실") == "official"
    assert source_leaning("듣보잡신문") == "unknown"
    assert source_leaning(None) == "unknown"


def test_source_leaning_partial_match():
    assert source_leaning("한겨레신문") == "left"


def test_bias_breakdown_counts_and_blindspot():
    arts = [{"source": "한겨레"}, {"source": "경향신문"}, {"source": "연합뉴스"}]
    out = bias_breakdown(arts)
    assert out["counts"]["left"] == 2
    assert out["counts"]["center"] == 1
    assert out["counts"]["right"] == 0
    assert out["total"] == 3
    assert out["blindspot"] == "right"


def test_bias_breakdown_no_blindspot_when_both_sides():
    arts = [{"source": "한겨레"}, {"source": "동아일보"}]
    out = bias_breakdown(arts)
    assert out["blindspot"] is None


def test_bias_breakdown_empty():
    out = bias_breakdown([])
    assert out["total"] == 0 and out["blindspot"] is None
