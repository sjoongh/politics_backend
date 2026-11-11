"""Gemini 일일 호출 예산 (무료 티어 20건/일 공유).

전체 한도와 종류별 한도를 둘 다 적용한다. 상태는 store(get/set dict)에 저장되며
운영에서는 Firestore `_meta/ai_budget_{YYYY-MM-DD}` 문서, 테스트는 dict 가짜.
429를 받으면 mark_exhausted()로 그날 남은 호출을 즉시 거부한다.
"""
import os
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
DEFAULT_LIMIT = 18
DEFAULT_PER_KIND = {"summary": 10, "enrich": 8, "stance": 0, "article": 0, "daily": 1}


def _env_int(name, default):
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


class AiBudget:
    def __init__(self, limit: int, today: str, store, per_kind=None):
        self.limit = limit
        self.today = today
        self.store = store
        self.per_kind = dict(DEFAULT_PER_KIND if per_kind is None else per_kind)

    def _state(self):
        """저장소 상태. 읽기 실패는 None(= 거부). 하드 쿼터라 장애 시 열어두지 않는다."""
        try:
            st = self.store.get() or {}
        except Exception:  # noqa: BLE001
            return None
        if st.get("date") != self.today:
            st = {"date": self.today, "used": 0, "by_kind": {}, "exhausted": False}
        st.setdefault("by_kind", {})
        return st

    def used(self) -> int:
        st = self._state()
        return int(st.get("used", 0)) if st else 0

    def _reserve(self, st: dict, kind: str, n: int):
        """상태 dict에 예약을 반영한 새 상태와 승인 여부(순수)."""
        if st.get("date") != self.today:
            st = {"date": self.today, "used": 0, "by_kind": {}, "exhausted": False}
        st = {**st, "by_kind": dict(st.get("by_kind") or {})}
        if st.get("exhausted") or st.get("used", 0) + n > self.limit:
            return st, False
        cap = self.per_kind.get(kind)
        if cap is not None and st["by_kind"].get(kind, 0) + n > cap:
            return st, False
        st["used"] = st.get("used", 0) + n
        st["by_kind"][kind] = st["by_kind"].get(kind, 0) + n
        return st, True

    def try_acquire(self, kind: str, n: int = 1) -> bool:
        cap = self.per_kind.get(kind)
        if cap is not None and cap < n:
            return False            # 상한 0인 종류는 저장소를 읽지 않고 거부(매시 기사 수집 경로)
        # 저장소가 원자적 갱신을 지원하면(운영: Firestore 트랜잭션) 검사와 증가를 한 번에. 실패는 거부.
        if hasattr(self.store, "atomic"):
            try:
                return bool(self.store.atomic(lambda cur: self._reserve(cur or {}, kind, n)))
            except Exception:  # noqa: BLE001
                return False
        st = self._state()
        if st is None or st.get("exhausted"):
            return False
        if st["used"] + n > self.limit:
            return False
        if cap is not None and st["by_kind"].get(kind, 0) + n > cap:
            return False
        st["used"] += n
        st["by_kind"][kind] = st["by_kind"].get(kind, 0) + n
        self.store.set(st)
        return True

    def mark_exhausted(self) -> None:
        st = self._state() or {"date": self.today, "used": 0, "by_kind": {}}
        st["exhausted"] = True
        try:
            self.store.set(st)
        except Exception:  # noqa: BLE001
            pass


class _FirestoreStore:
    def __init__(self, doc_id: str):
        self.doc_id = doc_id

    def _ref(self):
        from firebase.firebase_config import db
        return db.collection("_meta").document(self.doc_id)

    def get(self) -> dict:
        snap = self._ref().get()          # 실패는 AiBudget._state()가 None(거부)으로 처리
        return snap.to_dict() or {} if snap.exists else {}

    def set(self, v: dict) -> None:
        try:
            self._ref().set(v)
        except Exception:  # noqa: BLE001
            pass

    def atomic(self, fn) -> bool:
        """트랜잭션: 현재 상태를 읽고 fn(cur)->(new, ok); ok면 쓰기. 커밋 실패는 예외로 올린다(호출 측에서 거부)."""
        from firebase.firebase_config import db
        from google.cloud import firestore as _fs
        ref = self._ref()

        @_fs.transactional
        def _run(tx):
            snap = ref.get(transaction=tx)
            cur = (snap.to_dict() or {}) if snap.exists else {}
            new, ok = fn(cur)
            if ok:
                tx.set(ref, new)
            return ok
        return _run(db.transaction())


_BUDGET = None


def budget() -> AiBudget:
    """프로세스 싱글턴. 날짜가 바뀌면 새 문서를 본다."""
    global _BUDGET
    today = datetime.now(KST).strftime("%Y-%m-%d")
    if _BUDGET is None or _BUDGET.today != today:
        per_kind = dict(DEFAULT_PER_KIND)
        if os.getenv("STANCE_PRESS", "0").strip() in ("1", "true", "yes", "on"):
            per_kind["stance"] = 4
        per_kind["article"] = _env_int("GEMINI_ARTICLE_CAP", 0)   # 기사별 AI 요약(기본 0: RSS 요약 저장)
        _BUDGET = AiBudget(limit=_env_int("GEMINI_DAILY_BUDGET", DEFAULT_LIMIT), today=today,
                           store=_FirestoreStore(f"ai_budget_{today}"), per_kind=per_kind)
    return _BUDGET
