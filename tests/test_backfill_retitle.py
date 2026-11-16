"""backfill retitle의 이슈 1건 변환(순수 부분)."""
from datetime import datetime, timezone
from scripts.backfill_issues import _retitle_news, _retitle_bill

NOW = datetime(2026, 11, 16, tzinfo=timezone.utc)


def test_retitle_news_quote_centered_people_by_frequency_and_summary():
    iss = {"id": "n", "auto_key": "news:1", "title": "김민석 ‘하이에나 떼들’", "keywords": ["하이에나 떼들", "김민석", "최민희"],
           "entities": {"people": ["김민석", "최민희"]}, "summary": "외교부, 이란 파병 자제 촉구", "ai_summarized": False,
           "status": "진행중", "digest": {"last_activity_at": "2026-11-13T00:00:00+00:00"},
           "article_meta": {"a": {"leaning": "center", "at": "2026-11-13"}, "b": {"leaning": "left", "at": "2026-11-12"}}}
    arts = [{"id": "a", "title": "외교부, 이란 파병 자제 촉구", "ai_summary": ""},
            {"id": "b", "title": "최민희 '하이에나 떼들' 발언 사과", "ai_summary": "최민희 의원이 사과했다"}]
    p = _retitle_news(iss, arts, {"김민석", "최민희"}, NOW)
    assert p["title"] == "‘하이에나 떼들’ 논란"
    assert p["entities"]["people"][0] == "최민희"
    assert p["summary"] == "최민희 '하이에나 떼들' 발언 사과"
    assert "status" not in p


def test_retitle_news_replaces_english_ai_summary_and_quiets_old():
    iss = {"id": "n", "auto_key": "news:2", "title": "진성준 ‘대주주 기준’", "keywords": ["대주주 기준", "진성준"],
           "entities": {"people": ["진성준"]}, "summary": "The political issue revolves around", "ai_summarized": True,
           "status": "진행중", "digest": {"last_activity_at": "2025-08-02T00:00:00+00:00"},
           "article_meta": {"a": {"leaning": "center", "at": "2025-08-02"}}}
    p = _retitle_news(iss, [{"id": "a", "title": "'대주주 기준' 강화 논쟁", "ai_summary": ""}], {"진성준"}, NOW)
    assert p["summary"] == "'대주주 기준' 강화 논쟁" and p["ai_summarized"] is False and p["status"] == "소강"


def test_retitle_bill_summary_and_procedural_retire():
    bill = {"id": "b", "auto_key": "bill:1", "title": "국민연금법 일부개정법률안(대안)(보건복지위원장)", "law_name": "국민연금법",
            "status": "가결", "summary": "국민연금법 · 가결 · 11.10",
            "digest": {"counts": {"media": 0, "vote": 1},
                       "vote": {"date": "2026-08-20", "yes": 156, "no": 9, "abstain": 12, "result": "가결"}}}
    p = _retitle_bill(bill)
    assert p["summary"] == "가결 · 8.20 표결 · 찬성 156 · 반대 9 · 기권 12" and "active" not in p
    proc = {"id": "p", "auto_key": "bill:2", "title": "제437회국회(임시회) 회기결정의 건(국회운영위원장)", "status": "가결",
            "digest": {"counts": {"media": 0, "vote": 1}, "vote": {"date": "2026-07-30", "yes": 113, "no": 83, "abstain": 0, "result": "가결"}}}
    p = _retitle_bill(proc)
    assert p["active"] is False and p["inactive_reason"] == "gate" and "retired_reason" not in p
    # digest가 낡아 media=0이어도 실제 기사 메타가 있으면 비활성하지 않는다
    proc["article_meta"] = {"a": {"at": "2026-07-30"}}
    assert "active" not in _retitle_bill(proc)
