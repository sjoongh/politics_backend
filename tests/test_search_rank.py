"""AI 검색 랭킹 순수 로직 테스트."""
from datetime import datetime, timezone
from utils.search_rank import rank_articles, score_article

NOW = datetime(2026, 6, 15, tzinfo=timezone.utc)

ARTS = [
    {"id": "a1", "title": "이재명 부동산 정책", "ai_summary": "부동산 대책",
     "category": "정치", "keywords": ["이재명", "부동산"], "published_at": "2026-06-14T09:00:00Z"},
    {"id": "a2", "title": "국회 추경 통과", "ai_summary": "추경 가결",
     "category": "국회", "keywords": ["추경", "예산"], "published_at": "2026-06-13T09:00:00Z"},
    {"id": "a3", "title": "날씨 맑음", "ai_summary": "전국 맑음",
     "category": "사회", "keywords": ["날씨"], "published_at": "2026-01-01T09:00:00Z"},
]


def test_relevance_gating_excludes_irrelevant_recent():
    """내용 무관 기사는 최신/카테고리만으로 통과하지 못한다."""
    parsed = {"keywords": ["부동산"], "category": "정치", "entities": ["이재명"],
              "parties": [], "date_preset": "recent"}
    ranked = rank_articles(ARTS, parsed, query="이재명 부동산", limit=10, now=NOW)
    ids = [r["id"] for r in ranked]
    assert "a1" in ids
    assert "a2" not in ids  # 무관한 최신 국회 기사 제외
    assert "a3" not in ids


def test_fallback_substring():
    """parsed 없이 부분문자열 폴백."""
    ranked = rank_articles(ARTS, None, query="추경", limit=10, now=NOW)
    assert ranked and ranked[0]["id"] == "a2"


def test_fallback_token_match_long_query():
    """긴 자연어 질의도 토큰 단위로 폴백 매칭."""
    ranked = rank_articles(ARTS, None, query="이재명 부동산 최근 입장", limit=10, now=NOW)
    assert any(r["id"] == "a1" for r in ranked)


def test_defensive_non_list_keywords():
    """keywords가 비리스트/비문자여도 죽지 않는다."""
    arts = [{"id": "x", "title": "추경 예산", "ai_summary": "", "keywords": None,
             "published_at": "2026-06-14T09:00:00Z"},
            {"id": "y", "title": "추경", "ai_summary": "", "keywords": [123, None],
             "published_at": "2026-06-14T09:00:00Z"}]
    ranked = rank_articles(arts, None, query="추경", limit=10, now=NOW)
    assert len(ranked) == 2


def test_score_zero_for_no_match():
    s, reasons = score_article(ARTS[2], {"keywords": ["부동산"], "category": None,
                               "entities": [], "parties": [], "date_preset": None}, "부동산", NOW)
    assert s == 0.0 and reasons == []
