"""이슈 digest 갱신 — 파이프라인 끝에서 변경된 이슈만 다시 계산해 저장한다.

읽기 예산 원칙: 기사를 다시 읽지 않는다(article_meta 사용). 소스는 이슈별 array_contains 조회
또는 호출자가 넘긴 sources_by_issue(이미 메모리에 있는 것)를 쓴다. 값이 같으면 쓰지 않는다.
"""
import os
from datetime import datetime, timezone
from firebase.firebase_config import db
from utils.issue_digest import build_digest

COLLECTION = "issues"


def _press_enabled() -> bool:
    return os.getenv("STANCE_PRESS", "0").strip().lower() in ("1", "true", "yes", "on")


def _same_digest(a: dict, b: dict) -> bool:
    strip = lambda d: {k: v for k, v in (d or {}).items() if k != "rank_at"}
    return strip(a) == strip(b)


class IssueDigestService:
    @staticmethod
    def _load_issues(issue_ids):
        if issue_ids is None:
            return [{**d.to_dict(), "id": d.id} for d in db.collection(COLLECTION).stream()
                    if d.to_dict().get("active") is not False]
        out = []
        for i in issue_ids:
            snap = db.collection(COLLECTION).document(i).get()
            if snap.exists:
                out.append({**snap.to_dict(), "id": snap.id})
        return out

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
            # ctx의 이슈는 파이프라인 중 갱신된 patch가 반영돼 있어 재조회 없이 쓴다
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
            if patch:
                db.collection(COLLECTION).document(iss["id"]).update(patch)
                iss.update(patch)   # ctx 공유 목록도 갱신(판 생성이 같은 실행에서 digest를 본다)
                updated += 1
        return {"success": True, "message": "digest 갱신", "data": {"scanned": scanned, "updated": updated}}


issue_digest_service = IssueDigestService()
