from utils.fallback_summary import fallback_summary


def test_news_prefers_center_latest():
    iss = {"auto_key": "news:1", "title": "t",
           "article_meta": {"a": {"leaning": "left", "at": "2026-11-10"}, "b": {"leaning": "center", "at": "2026-11-09"}}}
    arts = {"a": {"title": "한겨레 제목"}, "b": {"title": "연합 제목"}}
    assert fallback_summary(iss, arts) == "연합 제목"


def test_news_without_center_uses_latest():
    iss = {"auto_key": "news:1", "title": "t",
           "article_meta": {"a": {"leaning": "left", "at": "2026-11-10"}, "b": {"leaning": "right", "at": "2026-11-09"}}}
    assert fallback_summary(iss, {"a": {"title": "A"}, "b": {"title": "B"}}) == "A"


def test_bill_format_uses_vote_not_updated_at():
    # 법률명은 제목에 이미 있으므로 반복하지 않고, 날짜는 문서 수정일이 아니라 표결일
    iss = {"auto_key": "bill:1", "law_name": "국민연금법", "status": "가결", "updated_at": "2026-11-10",
           "digest": {"vote": {"date": "2026-08-20", "yes": 156, "no": 9, "abstain": 12, "result": "가결"}}}
    assert fallback_summary(iss, {}) == "가결 · 8.20 표결 · 찬성 156 · 반대 9 · 기권 12"


def test_bill_without_vote_uses_record_date():
    assert fallback_summary({"auto_key": "bill:1", "law_name": "국민연금법", "status": "진행중",
                             "updated_at": "2026-11-10", "record_date": "2026-11-08"}, {}) == "국민연금법 · 진행중 · 11.8"


def test_news_prefers_article_containing_phrase():
    # 최신 중도 기사라도 제목 인용구가 없으면(오염 연결) 뒤로
    iss = {"auto_key": "news:1", "title": "‘하이에나 떼들’ 논란", "keywords": ["하이에나 떼들", "최민희"],
           "entities": {"people": ["최민희"]},
           "article_meta": {"a": {"leaning": "center", "at": "2026-11-13"}, "b": {"leaning": "left", "at": "2026-11-12"}}}
    arts = {"a": {"title": "외교부, 이란 파병 자제 촉구에"}, "b": {"title": "최민희 '하이에나 떼' 발언 사과"}}
    arts["b"]["title"] = "최민희 '하이에나 떼들' 발언 사과"
    assert fallback_summary(iss, arts) == "최민희 '하이에나 떼들' 발언 사과"


def test_news_long_phrase_matches_by_tokens_and_no_match_returns_title():
    iss = {"auto_key": "news:1", "title": "‘한동훈 국힘 복당 반대…우리 당에 얼씬도 말라’ 논란",
           "keywords": ["한동훈 국힘 복당 반대…우리 당에 얼씬도 말라", "안철수", "한동훈"],
           "entities": {"people": ["안철수", "한동훈"]},
           "article_meta": {"a": {"leaning": "center", "at": "2026-11-13"}, "b": {"leaning": "left", "at": "2026-11-12"},
                            "c": {"leaning": "right", "at": "2026-11-11"}}}
    arts = {"a": {"title": "국힘 대구시당, 남구의회 의장 징계"}, "b": {"title": "안철수 \"한동훈 복당 반대…당에 얼씬도 마라\""},
            "c": {"title": "처음 묶인 기사"}}
    assert fallback_summary(iss, arts) == arts["b"]["title"]          # 핵심어(복당·당에·얼씬도) 절반 이상
    arts["b"]["title"] = "무관한 제목"
    assert fallback_summary(iss, arts) == iss["title"]                 # 일치 없음 → 근거 없는 요약 대신 제목(화면은 숨김)


def test_never_empty():
    assert fallback_summary({"auto_key": "news:1", "title": "제목만"}, {}) == "제목만"


def test_is_korean():
    from utils.gemini_rest import is_korean
    assert is_korean("김민석 대표가 'AI 기본법' 처리를 촉구했다.")
    assert not is_korean("The political issue revolves around the 'major shareholder' standard.")
    assert not is_korean("")
