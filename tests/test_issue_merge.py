from datetime import datetime, timezone
from utils.issue_merge import top_person, clean_title, should_merge, merge_plan

NOW = datetime(2026, 11, 10, tzinfo=timezone.utc)


def test_top_person():
    assert top_person([{"entities": {"people": ["권영진", "정점식"]}}, {"entities": {"people": ["권영진"]}}]) == "권영진"


def test_top_person_none():
    assert top_person([{"entities": {"people": []}}]) is None


def test_clean_title_strips_name():
    assert clean_title("김승원", "김승원 공세") == "김승원 ‘공세’"


def test_clean_title_without_name_or_phrase():
    assert clean_title(None, "멱살 파문") == "‘멱살 파문’ 논란"
    assert clean_title("권영진", "") == "권영진 관련 현안"
    assert clean_title("권영진", "권영진") == "권영진 관련 현안"


def test_merge_requires_same_person():
    c = {"article_ids": {"a", "b", "c"}, "person": "권영진", "phrases": ["멱살 파문"]}
    iss = {"entities": {"people": ["김승원"]}, "article_ids": ["a", "b", "c"], "keywords": ["멱살"],
           "updated_at": "2026-11-09T00:00:00+00:00"}
    assert not should_merge(c, iss, NOW)


def test_article_overlap_alone_does_not_merge():
    # 인명 단독 크로스링크로 오염된 기사 집합은 겹침이 커도 다른 사건일 수 있다(라이브 dry-run 근거)
    c = {"article_ids": {"a", "b", "x"}, "person": "김민석", "phrases": ["호남 현장에서 답 찾겠다"]}
    iss = {"entities": {"people": ["김민석"]}, "article_ids": ["a", "b", "c", "d"], "keywords": ["한중, 더 단단해진 길 걸어", "김민석"],
           "updated_at": "2026-11-09T00:00:00+00:00"}
    assert not should_merge(c, iss, NOW)


def test_merge_by_token_jaccard():
    c = {"article_ids": set(), "person": "이진숙", "phrases": ["5·18 왜곡 입장 밝혀라"]}
    iss = {"entities": {"people": ["이진숙"]}, "article_ids": [], "keywords": ["5·18 왜곡 입장 즉각 밝혀라", "이진숙"],
           "updated_at": "2026-11-09T00:00:00+00:00"}
    assert should_merge(c, iss, NOW)   # 토큰 {5·18, 왜곡, 입장, 밝혀라} / {…, 즉각} = 4/5


def test_merge_by_phrase_containment():
    c = {"article_ids": {"x"}, "person": "권영진", "phrases": ["멱살 파문"]}
    iss = {"entities": {"people": ["권영진"]}, "article_ids": ["a"], "keywords": ["멱살 파문 징계"],
           "updated_at": "2026-11-09T00:00:00+00:00"}
    assert should_merge(c, iss, NOW)


def test_short_phrase_merges_only_via_token_jaccard():
    c = {"article_ids": {"x"}, "person": "권영진", "phrases": ["멱살 파문"]}
    iss = {"entities": {"people": ["권영진"]}, "article_ids": ["a"], "keywords": ["멱살"],
           "updated_at": "2026-11-09T00:00:00+00:00"}
    assert should_merge(c, iss, NOW)      # 토큰 {멱살,파문}∩{멱살} → 1/2 = 0.5
    iss["keywords"] = ["징계"]
    assert not should_merge(c, iss, NOW)  # 공통 토큰 없음


def test_merge_stale_issue_not_merged():
    c = {"article_ids": {"a", "b"}, "person": "권영진", "phrases": ["멱살 파문"]}
    iss = {"entities": {"people": ["권영진"]}, "article_ids": ["a", "b"], "keywords": ["멱살 파문"],
           "updated_at": "2026-01-01T00:00:00+00:00"}
    assert not should_merge(c, iss, NOW)


def test_merge_uses_digest_last_activity():
    c = {"article_ids": {"a", "b"}, "person": "권영진", "phrases": ["멱살 파문"]}
    iss = {"entities": {"people": ["권영진"]}, "article_ids": ["a", "b"], "keywords": ["멱살 파문"],
           "updated_at": "2026-01-01", "digest": {"last_activity_at": "2026-11-09T00:00:00+00:00"}}
    assert should_merge(c, iss, NOW)


def test_merge_plan_keeps_oldest_once():
    a = {"id": "a", "started_at": "2026-10-01", "auto_key": "news:a", "entities": {"people": ["권영진"]},
         "article_ids": ["1", "2", "3"], "keywords": ["멱살 파문"], "updated_at": "2026-11-09"}
    b = {"id": "b", "started_at": "2026-10-05", "auto_key": "news:b", "entities": {"people": ["권영진"]},
         "article_ids": ["1", "2"], "keywords": ["멱살 파문 징계"], "updated_at": "2026-11-09"}
    assert merge_plan([b, a], NOW) == [("b", "a")]


def test_merge_plan_skips_merged_and_non_news():
    a = {"id": "a", "started_at": "2026-10-01", "auto_key": "news:a", "entities": {"people": ["권영진"]},
         "article_ids": ["1", "2"], "keywords": ["멱살 파문"], "updated_at": "2026-11-09", "merged_into": "z"}
    b = {"id": "b", "started_at": "2026-10-05", "auto_key": "news:b", "entities": {"people": ["권영진"]},
         "article_ids": ["1", "2"], "keywords": ["멱살 파문"], "updated_at": "2026-11-09"}
    m = {"id": "m", "started_at": "2026-09-01", "entities": {"people": ["권영진"]},
         "article_ids": ["1", "2"], "keywords": ["멱살 파문"], "updated_at": "2026-11-09"}
    assert merge_plan([a, b, m], NOW) == []


def test_merge_plan_stale_days_override_for_one_off_cleanup():
    a = {"id": "a", "started_at": "2026-07-01", "auto_key": "news:a", "entities": {"people": ["권영진"]},
         "article_ids": ["1"], "keywords": ["멱살 파문"], "digest": {"last_activity_at": "2026-08-10T00:00:00+00:00"}}
    b = {"id": "b", "started_at": "2026-07-05", "auto_key": "news:b", "entities": {"people": ["권영진"]},
         "article_ids": ["2"], "keywords": ["멱살"], "digest": {"last_activity_at": "2026-08-12T00:00:00+00:00"}}
    assert merge_plan([a, b], NOW) == []
    assert merge_plan([a, b], NOW, stale_days=None) == [("b", "a")]
