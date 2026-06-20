from utils.news_cluster import cluster_articles


def _a(id, src, names, phrases, day):
    return {"id": id, "source": src, "published_at": f"2026-06-{day:02d}T09:00:00Z",
            "entities": {"names": names, "parties": [], "phrases": phrases}}


def test_same_story_clusters_by_name_and_phrase_token():
    arts = [
        _a("a1", "연합", ["진성준"], ["대주주 기준 완화"], 18),
        _a("a2", "한겨레", ["진성준"], ["대주주 기준"], 18),     # 다른 출처, 같은 인물+대주주
        _a("a3", "조선", ["김건희"], ["특검"], 18),              # 무관
    ]
    clusters = cluster_articles(arts, min_articles=2, min_sources=2)
    assert len(clusters) == 1
    c = clusters[0]
    assert set(c["article_ids"]) == {"a1", "a2"}
    assert c["sources"] == 2
    assert "진성준" in c["names"]


def test_single_source_not_promoted():
    arts = [
        _a("a1", "연합", ["진성준"], ["대주주 기준"], 18),
        _a("a2", "연합", ["진성준"], ["대주주 기준"], 18),     # 같은 출처 2건 → 미승격
    ]
    assert cluster_articles(arts, min_articles=2, min_sources=2) == []


def test_window_excludes_far_apart():
    arts = [
        _a("a1", "연합", ["진성준"], ["대주주"], 1),
        _a("a2", "한겨레", ["진성준"], ["대주주"], 18),         # 17일 차 → 윈도우 밖
    ]
    assert cluster_articles(arts, window_days=7, min_articles=2, min_sources=2) == []
