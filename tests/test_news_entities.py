from utils.news_entities import extract_phrases, extract_entities, normalize_phrase


def test_extract_quoted_phrases():
    t = "진성준, ‘대주주 기준 완화’ 공개 반대…“주식시장 안 무너져”"
    ph = extract_phrases(t)
    assert "대주주 기준 완화" in ph
    assert "주식시장 안 무너져" in ph


def test_extract_entities_names_and_parties():
    e = extract_entities("진성준 \"주식시장 안무너진다\"…'대주주 기준' 놓고 與공방 확대",
                         "", known_names={"진성준", "이재명"})
    assert "진성준" in e["names"]
    assert "대주주 기준" in e["phrases"]


def test_party_detection():
    e = extract_entities("국민의힘 \"종전합의 다행\"", "민주당 반발", known_names=set())
    assert "국민의힘" in e["parties"]
    assert "민주당" in e["parties"]


def test_normalize_phrase():
    assert normalize_phrase("  대주주  기준 ") == "대주주 기준"
    assert normalize_phrase("대주주 기준 완화") == "대주주 기준 완화"
