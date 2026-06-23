from utils.party_stance import detect_parties, group_by_party


def test_detect_parties_dedup():
    assert detect_parties("더불어민주당 논평") == ["더불어민주당"]   # 민주당 중복 제외
    assert set(detect_parties("국민의힘과 조국혁신당 공방")) == {"국민의힘", "조국혁신당"}
    assert detect_parties("날씨 맑음") == []


def test_group_by_party_counts_and_sorts():
    arts = [
        {"title": "국민의힘 '종전 다행'", "ai_summary": "", "source": "연합", "source_url": "u1"},
        {"title": "국민의힘 추가 입장", "ai_summary": "", "source": "한겨레", "source_url": "u2"},
        {"title": "진성준 대주주 반대", "ai_summary": "더불어민주당 입장", "source": "조선", "source_url": "u3"},
    ]
    g = group_by_party(arts)
    assert g[0]["party"] == "국민의힘" and g[0]["count"] == 2   # 최다 먼저
    parties = {x["party"] for x in g}
    assert "더불어민주당" in parties
