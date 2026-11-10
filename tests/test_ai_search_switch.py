"""AI 검색의 Gemini 호출 스위치(AI_SEARCH_GEMINI) — 기본 꺼짐, 켜면 기존 경로."""
import asyncio

import utils.gemini_rest as g


def test_default_off(monkeypatch):
    monkeypatch.delenv("AI_SEARCH_GEMINI", raising=False)
    assert g.search_gemini_enabled() is False


def test_env_on(monkeypatch):
    monkeypatch.setenv("AI_SEARCH_GEMINI", "1")
    assert g.search_gemini_enabled() is True
    monkeypatch.setenv("AI_SEARCH_GEMINI", "off")
    assert g.search_gemini_enabled() is False


def test_parse_and_briefing_skip_gemini_when_off(monkeypatch):
    monkeypatch.delenv("AI_SEARCH_GEMINI", raising=False)
    async def boom(*a, **k):
        raise AssertionError("Gemini must not be called when disabled")
    monkeypatch.setattr(g, "_generate", boom)
    assert asyncio.run(g.parse_query("대주주 기준")) == (None, "disabled")
    assert asyncio.run(g.synthesize_briefing("q", [{"id": "a"}])) == (None, "disabled")


def test_parse_calls_gemini_when_on(monkeypatch):
    monkeypatch.setenv("AI_SEARCH_GEMINI", "1")
    called = []
    async def fake(prompt, *, json_mode, timeout):
        called.append(prompt)
        return '{"keywords": ["대주주"], "entities": [], "time_range_days": null}', None
    monkeypatch.setattr(g, "_generate", fake)
    g._PARSE_CACHE.clear() if hasattr(g._PARSE_CACHE, "clear") else None
    parsed, reason = asyncio.run(g.parse_query("대주주 기준 테스트 " + "x"))
    assert called and parsed is not None
