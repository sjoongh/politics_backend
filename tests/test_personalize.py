"""개인화 추천 순수 로직 테스트."""
from utils.personalize import (
    build_profile, pick_reason, diversify, implicit_keywords, normalize_terms,
)


def test_normalize_terms_dedup_lower():
    assert normalize_terms(["부동산", "부동산", " 경제 ", "경제"]) == ["부동산", "경제"]


def test_implicit_keywords_by_frequency():
    bms = [{"keywords": ["부동산", "집값"]}, {"keywords": ["부동산", "정책"]}, {"keywords": ["이재명"]}]
    imp = implicit_keywords(bms, top_n=5)
    assert imp[0] == "부동산"  # 최빈


def test_build_profile_merges_and_dedups():
    bms = [{"keywords": ["부동산", "정책"]}]
    parsed, explicit, implicit = build_profile(["부동산", "경제"], bms)
    assert isinstance(explicit, list) and isinstance(implicit, list)  # 결정성용 리스트
    assert "부동산" in explicit and "부동산" not in implicit  # 명시 우선, 암묵서 제외
    assert parsed["date_preset"] == "recent"


def test_pick_reason_deterministic_and_priority():
    _, explicit, implicit = build_profile(["부동산"], [{"keywords": ["집값"]}])
    art = {"title": "부동산 집값 동향", "keywords": []}
    r1 = pick_reason(art, explicit, implicit)
    r2 = pick_reason(art, explicit, implicit)
    assert r1 == r2                 # 결정적
    assert "부동산" in r1            # 명시 관심사 우선


def test_pick_reason_fallback():
    assert pick_reason({"title": "무관 기사", "keywords": []}, ["부동산"], []) == "최근 주요 정치뉴스"


def test_diversify_source_cap():
    items = [{"id": i, "category": "정치", "source": "A"} for i in range(5)]
    out = diversify(items, limit=10, max_per_source=3)
    assert len([o for o in out if o["source"] == "A"]) <= 3


def test_diversify_breaks_category_run():
    items = (
        [{"id": i, "category": "정치", "source": f"s{i}"} for i in range(4)]
        + [{"id": 10, "category": "경제", "source": "x"}, {"id": 11, "category": "사회", "source": "y"}]
    )
    cats = [o["category"] for o in diversify(items, limit=6, max_per_source=9, max_category_run=2)]
    run = 1
    for i in range(1, len(cats)):
        run = run + 1 if cats[i] == cats[i - 1] else 1
        assert run <= 2  # 같은 카테고리 3연속 없음
