"""파이프라인 실행 내 공유 로더 — 기사·활성 이슈·최근 소스·의원명을 실행당 한 번만 읽는다(읽기 예산)."""
from datetime import datetime, timedelta, timezone
from utils.edition import kst_date


class PipelineContext:
    def __init__(self, load_articles, load_issues, load_sources, load_member_names, now_iso=None):
        self._la, self._li, self._ls, self._ln = load_articles, load_issues, load_sources, load_member_names
        self._articles, self._articles_n = None, 0
        self._issues = None
        self._sources, self._sources_days = None, 0
        self._names = None
        self._changed = []
        self.now = datetime.fromisoformat(now_iso) if now_iso else datetime.now(timezone.utc)

    def articles(self, limit: int = 400) -> list:
        if self._articles is None or limit > self._articles_n:
            self._articles, self._articles_n = list(self._la(limit)), limit
        return self._articles

    def active_issues(self) -> list:
        if self._issues is None:
            self._issues = [i for i in self._li() if i.get("active") is not False]
        return self._issues

    def recent_sources(self, days: int = 14) -> list:
        if self._sources is None or days > self._sources_days:
            self._sources, self._sources_days = list(self._ls(days)), days
        cutoff = (self.now - timedelta(days=days)).strftime("%Y-%m-%d")
        return [s for s in self._sources if (kst_date(s.get("published_at")) or "") >= cutoff]

    def member_names(self) -> set:
        if self._names is None:
            self._names = set(self._ln())
        return self._names

    def mark_issue_changed(self, issue_id: str) -> None:
        if issue_id and issue_id not in self._changed:
            self._changed.append(issue_id)

    @property
    def changed_issue_ids(self) -> list:
        return list(self._changed)


def firestore_context(db) -> PipelineContext:
    """운영용: Firestore 로더로 컨텍스트 생성."""
    from google.cloud import firestore as _fs

    def la(limit):
        return [{**d.to_dict(), "id": d.id} for d in db.collection("articles")
                .order_by("published_at", direction=_fs.Query.DESCENDING).limit(limit).stream()]

    def li():
        return [{**d.to_dict(), "id": d.id} for d in db.collection("issues").stream()]

    def ls(days):
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        # 최신순으로 읽어 상한(600)에 걸려도 최신 소스가 남는다(I1)
        return [{**d.to_dict(), "id": d.id} for d in db.collection("source_items")
                .where("published_at", ">=", cutoff)
                .order_by("published_at", direction=_fs.Query.DESCENDING).limit(600).stream()]

    def ln():
        # _meta/member_names 캐시(7일) → 없거나 오래되면 전수 스캔 후 갱신. 300 읽기 → 1 읽기.
        meta = db.collection("_meta").document("member_names")
        try:
            snap = meta.get()
            if snap.exists:
                d = snap.to_dict() or {}
                at = datetime.fromisoformat(d.get("at")) if d.get("at") else None
                if at and datetime.now(timezone.utc) - at < timedelta(days=7) and d.get("names"):
                    return set(d["names"])
        except Exception:  # noqa: BLE001
            pass
        names = set()
        for d in db.collection("members").limit(500).stream():
            n = d.to_dict().get("name")
            if n and len(n) >= 2:
                names.add(n)
        try:
            meta.set({"names": sorted(names), "at": datetime.now(timezone.utc).isoformat()})
        except Exception:  # noqa: BLE001
            pass
        return names

    return PipelineContext(la, li, ls, ln)
