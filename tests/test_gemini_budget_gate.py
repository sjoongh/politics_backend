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


def test_generate_logs_error_body_excerpt(monkeypatch, capsys):
    """429 원인(분당 제한/일일 한도)을 실행 로그로 가를 수 있게 응답 본문 앞부분을 한 줄로 남긴다."""
    monkeypatch.setenv("GOOGLE_API_KEY", "k")
    b = AiBudget(limit=18, today="d", store=Mem(), per_kind={"enrich": 8})
    monkeypatch.setattr(g, "budget", lambda: b)
    body = '{"error": {"code": 429,\n "details": [{"quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"}]}}' + "x" * 2000

    class R:
        status_code = 429
        text = body

    class Client:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **k): return R()

    monkeypatch.setattr(g.httpx, "AsyncClient", Client)
    asyncio.run(g._generate("p", json_mode=True, timeout=1.0, kind="enrich"))
    lines = [l for l in capsys.readouterr().out.splitlines() if l.startswith("[gemini]")]
    assert len(lines) == 1
    assert "http_429" in lines[0] and "kind=enrich" in lines[0]
    assert "GenerateRequestsPerMinutePerProjectPerModel-FreeTier" in lines[0]
    assert len(lines[0]) < 1400
