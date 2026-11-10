import asyncio
import services.ai_service as mod
from utils.ai_budget import AiBudget


class Mem:
    def __init__(self): self.d = {}
    def get(self): return dict(self.d)
    def set(self, v): self.d = dict(v)


def test_article_summary_denied_without_budget_and_no_retry(monkeypatch):
    calls = []
    svc = mod.ai_summary_service
    monkeypatch.setattr(svc, "model", object())   # 모델이 있어도 예산에서 막혀야 한다
    monkeypatch.setattr(mod, "budget", lambda: AiBudget(limit=18, today="d", store=Mem()))  # article cap 기본 0
    monkeypatch.setattr(mod.asyncio, "to_thread", lambda *a, **k: calls.append(1))
    r = asyncio.run(svc.summarize_by_category("정치", "t", "c"))
    assert r["success"] is False and r.get("budget") is True and calls == []


def test_default_budget_article_cap_is_zero_and_env_raises_it(monkeypatch):
    b = AiBudget(limit=18, today="d", store=Mem())
    assert not b.try_acquire("article")
    b2 = AiBudget(limit=18, today="d", store=Mem(), per_kind={"article": 2})
    assert b2.try_acquire("article") and b2.try_acquire("article") and not b2.try_acquire("article")
