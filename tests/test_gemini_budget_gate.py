import asyncio
import utils.gemini_rest as g
from utils.ai_budget import AiBudget


class Mem:
    def __init__(self): self.d = {}
    def get(self): return dict(self.d)
    def set(self, v): self.d = dict(v)


def test_generate_refused_when_budget_denies(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "k")
    monkeypatch.setattr(g, "budget", lambda: AiBudget(limit=0, today="d", store=Mem()))
    text, reason = asyncio.run(g._generate("p", json_mode=True, timeout=1.0, kind="summary"))
    assert text is None and reason == "budget"


def test_generate_marks_exhausted_on_429(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "k")
    b = AiBudget(limit=18, today="d", store=Mem(), per_kind={"summary": 10})
    monkeypatch.setattr(g, "budget", lambda: b)

    class R:
        status_code = 429
        def json(self): return {}

    class Client:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **k): return R()

    monkeypatch.setattr(g.httpx, "AsyncClient", Client)
    text, reason = asyncio.run(g._generate("p", json_mode=True, timeout=1.0, kind="summary"))
    assert reason == "http_429"
    assert not b.try_acquire("summary")   # 그날 남은 호출 거부
