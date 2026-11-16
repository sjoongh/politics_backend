"""이슈 digest 갱신 — 파이프라인 끝에서 변경된 이슈만 다시 계산해 저장한다.

읽기 예산 원칙: 기사를 다시 읽지 않는다(article_meta 사용). 소스는 이슈별 array_contains 조회
또는 호출자가 넘긴 sources_by_issue(이미 메모리에 있는 것)를 쓴다. 값이 같으면 쓰지 않는다.

변경되지 않은 이슈도 ctx에 이미 올라온 것은 순위만 다시 계산한다(시간 감쇠). 이전에는 변경된 이슈만
계산해 사흘 지난 이슈가 같은 점수로 1위에 머물렀다(2026-11-16 관측). 추가 읽기 없음, 차이 0.1↑만 쓴다.
뉴스 이슈는 30일 무활동이면 '소강'. ctx(최근 30일) 밖으로 막 나간 이슈는 37~30일 구간 조회로 잡는다.
"""
import os
from datetime import datetime, timezone
from firebase.firebase_config import db
from datetime import timedelta
from utils.issue_digest import build_digest, rerank, news_status, QUIET_DAYS

COLLECTION = "issues"


def _press_enabled() -> bool:
    return os.getenv("STANCE_PRESS", "0").strip().lower() in ("1", "true", "yes", "on")


def _same_digest(a: dict, b: dict) -> bool:
    strip = lambda d: {k: v for k, v in (d or {}).items() if k != "rank_at"}
    return strip(a) == strip(b)


def _apply_dotted(doc: dict, patch: dict) -> None:
    """Firestore 점 표기 patch('digest.rank')를 메모리 문서에 중첩 반영."""
    for k, v in patch.items():
        if "." in k:
            head, tail = k.split(".", 1)
            doc.setdefault(head, {})
            if isinstance(doc[head], dict):
                doc[head] = {**doc[head], tail: v}
        else:
            doc[k] = v


class IssueDigestService:
    @staticmethod
    def _load_issues(issue_ids):
        if issue_ids is None:
            return [{**d.to_dict(), "id": d.id} for d in db.collection(COLLECTION).stream()
                    if d.to_dict().get("active") is not False]
        refs = [db.collection(COLLECTION).document(i) for i in issue_ids]
        if not refs:
            return []
        return [{**snap.to_dict(), "id": snap.id} for snap in db.get_all(refs) if snap.exists]

    @staticmethod
    def _sources_for(issue_id: str) -> list:
        seen, out = set(), []
        for q in (db.collection("source_items").where("issue_id", "==", issue_id),
                  db.collection("source_items").where("issue_ids", "array_contains", issue_id)):
            for d in q.stream():
                s = d.to_dict()
                sid = s.get("id") or d.id
                if sid in seen:
                    continue
                if issue_id not in (s.get("issue_ids") or []) and s.get("link_status") not in ("auto", "confirmed"):
                    continue
                seen.add(sid)
                s.setdefault("id", sid)
                out.append(s)
        return out

    def refresh(self, issue_ids=None, sources_by_issue=None, press=None, ctx=None) -> dict:
        press = _press_enabled() if press is None else press
        now = datetime.now(timezone.utc)
        if ctx is not None and issue_ids is None:
            issue_ids = ctx.changed_issue_ids
        if ctx is not None and issue_ids:
            wanted = set(issue_ids)
            issues = [i for i in ctx.active_issues() if i["id"] in wanted]
            # ctx의 이슈는 파이프라인 중 갱신된 patch가 반영돼 있어 재조회 없이 쓴다.
            # ctx 목록에 없는 id(이번 실행에서 새로 만든 문서 등)는 읽어서 포함한다(C1).
            missing = sorted(wanted - {i["id"] for i in issues})
            if missing:
                issues += self._load_issues(missing)
        else:
            issues = self._load_issues(issue_ids)
        updated = scanned = 0
        for iss in issues:
            scanned += 1
            sources = (sources_by_issue or {}).get(iss["id"]) if sources_by_issue else None
            if sources is None:
                sources = self._sources_for(iss["id"])
            press_stance = iss.get("press_stance") or [] if press or iss.get("press_stance") else []
            digest = build_digest(iss, sources, now, press_stance=press_stance)
            patch = {}
            if not _same_digest(iss.get("digest"), digest):
                patch["digest"] = digest
            if iss.get("active") is None:
                patch["active"] = True
            st = news_status(iss, digest.get("last_activity_at"), now)
            if st and st != iss.get("status"):
                patch["status"] = st
            if patch:
                db.collection(COLLECTION).document(iss["id"]).update(patch)
                iss.update(patch)   # ctx 공유 목록도 갱신(판 생성이 같은 실행에서 digest를 본다)
                updated += 1
        reranked = quieted = 0
        if ctx is not None:
            done = {i["id"] for i in issues}
            for iss in ctx.active_issues():
                if iss["id"] in done or iss.get("active") is False:
                    continue
                patch = self._decay_patch(iss, now)
                if patch:
                    db.collection(COLLECTION).document(iss["id"]).update(patch)
                    _apply_dotted(iss, patch)   # 같은 실행의 판 생성이 새 순위를 보게
                    reranked += 1
            quieted = self._sweep_quiet(now)
        return {"success": True, "message": "digest 갱신",
                "data": {"scanned": scanned, "updated": updated, "reranked": reranked, "quieted": quieted}}

    @staticmethod
    def _decay_patch(iss: dict, now) -> dict:
        patch = {}
        new = rerank(iss, now)
        if new is not None:
            patch["digest.rank"] = new
            patch["digest.rank_at"] = now.isoformat()
        st = news_status(iss, (iss.get("digest") or {}).get("last_activity_at"), now)
        if st and st != iss.get("status"):
            patch["status"] = st
        return patch

    @staticmethod
    def _sweep_quiet(now) -> int:
        """ctx 창(30일) 밖으로 막 나간 이슈(30~37일 무활동)를 소강 처리·순위 감쇠. 단일 필드 범위 조회(자동 인덱스)."""
        lo = (now - timedelta(days=QUIET_DAYS + 7)).isoformat()
        hi = (now - timedelta(days=QUIET_DAYS)).isoformat()
        n = 0
        try:
            q = (db.collection(COLLECTION).where("digest.last_activity_at", ">=", lo)
                 .where("digest.last_activity_at", "<", hi))
            for d in q.stream():
                iss = {**d.to_dict(), "id": d.id}
                if iss.get("active") is False:
                    continue
                patch = IssueDigestService._decay_patch(iss, now)
                if patch:
                    db.collection(COLLECTION).document(iss["id"]).update(patch)
                    n += 1
        except Exception as e:  # noqa: BLE001 — 정리 단계 실패가 digest 갱신 결과를 막지 않는다
            print(f"[sweep_quiet] {e!r}")
        return n


issue_digest_service = IssueDigestService()
