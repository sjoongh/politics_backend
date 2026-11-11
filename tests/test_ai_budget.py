from utils.ai_budget import AiBudget


class Mem:
    def __init__(self):
        self.d = {}

    def get(self):
        return dict(self.d)

    def set(self, v):
        self.d = dict(v)


def test_acquire_until_limit():
    b = AiBudget(limit=2, today="2026-11-10", store=Mem(), per_kind={"summary": 10})
    assert b.try_acquire("summary") and b.try_acquire("summary")
    assert not b.try_acquire("summary")
    assert b.used() == 2


def test_counts_per_kind():
    b = AiBudget(limit=5, today="2026-11-10", store=Mem(), per_kind={"stance": 2})
    b.try_acquire("stance", 2)
    assert b.store.get()["by_kind"]["stance"] == 2
    assert not b.try_acquire("stance")        # 종류별 한도


def test_default_stance_is_zero():
    assert not AiBudget(limit=18, today="d", store=Mem()).try_acquire("stance")


def test_default_kinds_summary_and_enrich():
    b = AiBudget(limit=18, today="d", store=Mem())
    assert all(b.try_acquire("summary") for _ in range(10)) and not b.try_acquire("summary")
    assert all(b.try_acquire("enrich") for _ in range(8)) and not b.try_acquire("enrich")


def test_exhausted_blocks_all():
    b = AiBudget(limit=18, today="d", store=Mem())
    b.mark_exhausted()
    assert not b.try_acquire("summary")


def test_new_day_resets():
    store = Mem()
    AiBudget(limit=1, today="2026-11-10", store=store, per_kind={"summary": 5}).try_acquire("summary")
    assert AiBudget(limit=1, today="2026-11-11", store=store, per_kind={"summary": 5}).try_acquire("summary")
