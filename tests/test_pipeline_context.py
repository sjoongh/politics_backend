from services.pipeline_context import PipelineContext


def test_loaders_run_once_and_share():
    calls = {"articles": 0, "issues": 0, "sources": 0, "names": 0}

    def la(limit):
        calls["articles"] += 1
        return [{"id": f"a{i}"} for i in range(limit)]

    def li():
        calls["issues"] += 1
        return [{"id": "i1", "active": True}]

    def ls(days):
        calls["sources"] += 1
        return [{"id": "s1", "published_at": "2026-11-10"}]

    def ln():
        calls["names"] += 1
        return {"김가"}

    ctx = PipelineContext(load_articles=la, load_issues=li, load_sources=ls, load_member_names=ln)
    assert len(ctx.articles(5)) == 5 and len(ctx.articles(3)) == 5     # 같은 캐시(더 큰 요청이 먼저면 재사용)
    assert ctx.active_issues() is ctx.active_issues()
    assert ctx.recent_sources(14) and ctx.recent_sources(3)             # 14일 캐시에서 3일 필터
    assert ctx.member_names() == {"김가"}
    assert calls == {"articles": 1, "issues": 1, "sources": 1, "names": 1}


def test_larger_article_request_reloads():
    calls = []
    ctx = PipelineContext(load_articles=lambda n: calls.append(n) or [{"id": str(i)} for i in range(n)],
                          load_issues=lambda: [], load_sources=lambda d: [], load_member_names=lambda: set())
    ctx.articles(3)
    ctx.articles(10)
    assert calls == [3, 10]


def test_changed_issue_ids():
    ctx = PipelineContext(load_articles=lambda n: [], load_issues=lambda: [], load_sources=lambda d: [],
                          load_member_names=lambda: set())
    ctx.mark_issue_changed("a"); ctx.mark_issue_changed("a"); ctx.mark_issue_changed("b")
    assert ctx.changed_issue_ids == ["a", "b"]


def test_recent_sources_filters_by_days():
    srcs = [{"id": "new", "published_at": "2026-11-10"}, {"id": "old", "published_at": "2026-10-01T00:00:00Z"}]
    ctx = PipelineContext(load_articles=lambda n: [], load_issues=lambda: [], load_sources=lambda d: srcs,
                          load_member_names=lambda: set(), now_iso="2026-11-10T12:00:00+00:00")
    assert [s["id"] for s in ctx.recent_sources(3)] == ["new"]
