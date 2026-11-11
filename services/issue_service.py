import uuid
from datetime import datetime

from firebase.firebase_config import db
from models.model import IssueSeed, EventSeed
from utils.issue_rules import (
    is_valid_status, to_summary, sort_events, article_public, patchable,
)
from utils.source_bias import source_leaning, bias_breakdown
from utils.issue_merge_rules import follow_merge
from utils.doc_order import order_by_ids
from utils.cursor import encode_cursor, decode_cursor, valid_page_cursor
from utils.article_meta import attach_articles
from utils.issue_list_query import build_query_plan

COLLECTION = "issues"


def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


class IssueService:
    @staticmethod
    async def create(seed: IssueSeed) -> dict:
        if not is_valid_status(seed.status):
            return {"success": False, "message": "잘못된 상태입니다."}
        issue_id = uuid.uuid4().hex
        now = _now()
        data = {
            **seed.dict(),
            "id": issue_id,
            "slug": seed.slug or issue_id,
            "started_at": now,
            "updated_at": now,
            "events": [],
            "article_ids": [],
            "article_meta": {},
            "active": True,
        }
        from utils.issue_digest import build_digest
        from datetime import timezone as _tz
        data["digest"] = build_digest(data, [], datetime.now(_tz.utc))
        db.collection(COLLECTION).document(issue_id).set(data)
        return {"success": True, "message": "이슈 생성 성공", "data": data}

    @staticmethod
    def list_summaries(status=None, category=None, limit: int = 20, offset: int = 0,
                       v=None, sort: str = "rank", filter=None, cursor=None) -> dict:
        if v == 2:
            return IssueService._list_v2(sort=sort, filter_=filter, cursor=cursor, limit=limit)
        query = db.collection(COLLECTION)
        if status:
            query = query.where("status", "==", status)
        if category:
            query = query.where("category", "==", category)
        # (v1 호환) 사건성 점수 내림차순 정렬. 혼재 필드라 파이썬 정렬.
        docs = [{**doc.to_dict(), "id": doc.id} for doc in query.limit(200).stream()]
        docs = [d for d in docs if d.get("active") is not False]

        def _rank(d):
            nw = d.get("newsworthiness")
            base = 1000 if not d.get("auto_generated") else (nw if nw is not None else 0)
            return (base, str(d.get("updated_at") or ""))
        docs.sort(key=_rank, reverse=True)
        items = [to_summary(d) for d in docs[offset:offset + limit]]
        return {"success": True, "message": "이슈 목록 조회 성공", "data": items}

    @staticmethod
    def _list_v2(sort: str, filter_, cursor, limit: int) -> dict:
        """서버 정렬·단일 필터·커서 페이지네이션. 깨진 커서는 첫 페이지."""
        from google.cloud import firestore as _fs
        plan = build_query_plan(sort, filter_)
        limit = max(1, min(int(limit or 50), 100))
        q = db.collection(COLLECTION)
        for f, op, val in plan["where"]:
            q = q.where(f, op, val)
        q = q.order_by(plan["order"], direction=_fs.Query.DESCENDING).order_by("__name__")
        cur = decode_cursor(cursor)
        if valid_page_cursor(cur, "k"):
            q = q.start_after([cur["k"], cur["i"]])
        snaps = list(q.limit(limit + 1).stream())
        has_more = len(snaps) > limit
        rows = [{**d.to_dict(), "id": d.id} for d in snaps[:limit]]
        items = [to_summary(d) for d in rows]
        nxt = None
        if has_more and rows:
            last = rows[-1]
            key = last
            for part in plan["order"].split("."):
                key = (key or {}).get(part) if isinstance(key, dict) else None
            nxt = encode_cursor({"k": key, "i": last["id"]})
        return {"success": True, "message": "이슈 목록 조회 성공",
                "data": {"items": items, "next_cursor": nxt, "sort": sort or "rank", "filter": filter_}}

    @staticmethod
    def resolve_issue_id(issue_id: str) -> str:
        """병합된 이슈면 남은 이슈 id로 해석(최대 3단, 순환 차단)."""
        def _lookup(i):
            snap = db.collection(COLLECTION).document(i).get()
            return snap.to_dict() if snap.exists else None
        return follow_merge(issue_id, _lookup)

    @staticmethod
    def _ordered_article_ids(issue: dict) -> list:
        """article_meta가 있으면 at 내림차순, 없으면 저장 순서(호환)."""
        ids = list(issue.get("article_ids") or [])
        meta = issue.get("article_meta") or {}
        if meta:
            ids.sort(key=lambda i: (meta.get(i) or {}).get("at") or "", reverse=True)
        return ids

    @staticmethod
    def _load_articles(ids: list) -> list:
        """기사 일괄 조회(get_all 1회) 후 요청 순서로 정렬. 없는 기사는 건너뜀."""
        if not ids:
            return []
        refs = [db.collection("articles").document(i) for i in ids]
        docs = [{**snap.to_dict(), "id": snap.id} for snap in db.get_all(refs) if snap.exists]
        return [article_public(d) for d in order_by_ids(docs, ids)]

    @staticmethod
    def _linked_sources(issue_id: str) -> list:
        """연결 소스: 구 필드(issue_id ==)와 신 필드(issue_ids array_contains) 합집합."""
        seen, out = set(), []
        for q in (db.collection("source_items").where("issue_id", "==", issue_id),
                  db.collection("source_items").where("issue_ids", "array_contains", issue_id)):
            for d in q.stream():
                s = d.to_dict()
                sid = s.get("id") or d.id
                if sid in seen:
                    continue
                seen.add(sid)
                s.setdefault("id", sid)
                out.append(s)
        return out

    @staticmethod
    def get_detail(issue_id: str, article_limit: int = 30) -> dict:
        issue_id = IssueService.resolve_issue_id(issue_id)
        doc = db.collection(COLLECTION).document(issue_id).get()
        if not doc.exists:
            return {"success": False, "message": "이슈를 찾을 수 없습니다."}
        issue = doc.to_dict()
        issue["id"] = doc.id
        issue["events"] = sort_events(issue.get("events", []))
        ids = IssueService._ordered_article_ids(issue)
        articles = IssueService._load_articles(ids[:article_limit])
        issue["articles"] = articles
        issue["article_total"] = len(ids)
        issue["articles_cursor"] = encode_cursor({"o": article_limit}) if len(ids) > article_limit else None

        meta = issue.get("article_meta") or {}
        # 성향 집계: 메타가 있으면 전체 연결 기사 기준(기사 재조회 없음), 없으면 로드한 페이지 기준
        bias_input = [{"source": m.get("source", "")} for m in meta.values()] if meta else articles
        groups = {"left": [], "center": [], "right": [], "foreign": [], "official": [], "unknown": []}
        for a in articles:
            groups[source_leaning(a.get("source", ""))].append({
                "title": a.get("title"),
                "source": a.get("source"),
                "source_url": a.get("source_url"),
            })
        issue["perspectives"] = {
            "breakdown": bias_breakdown(bias_input),
            "groups": groups,
            "disclaimer": "매체 성향 분류는 통용되는 기준을 참고한 값이며 절대적이지 않습니다.",
        }
        issue.pop("article_meta", None)   # 응답 크기 절약(내부 필드)

        def _public(s):
            return {k: s.get(k) for k in (
                "id", "type", "actor_type", "actor_name", "title", "summary",
                "claim_summary", "position", "source_bias", "url", "published_at", "bill", "vote")}
        si = IssueService._linked_sources(issue_id)
        ok = [s for s in si if s.get("link_status") in ("auto", "confirmed")
              or issue_id in (s.get("issue_ids") or [])]
        from utils.party_stance import group_by_party
        issue["source_panels"] = {
            "government": [_public(s) for s in ok if s.get("type") == "gov_policy"],
            "assembly_bill": [_public(s) for s in ok if s.get("type") == "assembly_bill"],
            "assembly_vote": [_public(s) for s in ok if s.get("type") == "assembly_vote"],
            "party": group_by_party(articles),   # 기사에서 도출한 정당별 언급(입장 아님)
        }
        return {"success": True, "message": "이슈 상세 조회 성공", "data": issue}

    @staticmethod
    def list_articles(issue_id: str, cursor=None, limit: int = 30) -> dict:
        issue_id = IssueService.resolve_issue_id(issue_id)
        doc = db.collection(COLLECTION).document(issue_id).get()
        if not doc.exists:
            return {"success": False, "message": "이슈를 찾을 수 없습니다."}
        ids = IssueService._ordered_article_ids(doc.to_dict())
        offset = decode_cursor(cursor).get("o")
        offset = offset if isinstance(offset, int) and offset >= 0 else 0
        page_ids = ids[offset:offset + limit]
        items = IssueService._load_articles(page_ids)
        nxt = encode_cursor({"o": offset + limit}) if offset + limit < len(ids) else None
        return {"success": True, "message": "이슈 기사 조회 성공",
                "data": {"items": items, "next_cursor": nxt, "total": len(ids)}}

    @staticmethod
    async def update(issue_id: str, fields: dict) -> dict:
        if "status" in (fields or {}) and not is_valid_status(fields["status"]):
            return {"success": False, "message": "잘못된 상태입니다."}
        ref = db.collection(COLLECTION).document(issue_id)
        if not ref.get().exists:
            return {"success": False, "message": "이슈를 찾을 수 없습니다."}
        safe = patchable(fields)
        safe["updated_at"] = _now()
        ref.update(safe)
        return {"success": True, "message": "이슈 수정 성공", "data": ref.get().to_dict()}

    @staticmethod
    async def add_event(issue_id: str, seed: EventSeed) -> dict:
        ref = db.collection(COLLECTION).document(issue_id)
        snap = ref.get()
        if not snap.exists:
            return {"success": False, "message": "이슈를 찾을 수 없습니다."}
        event = {**seed.dict(), "id": uuid.uuid4().hex}
        events = list(snap.to_dict().get("events", [])) + [event]
        ref.update({"events": events, "updated_at": _now()})
        IssueService._refresh_digest(issue_id)
        return {"success": True, "message": "이벤트 추가 성공", "data": ref.get().to_dict()}

    @staticmethod
    async def add_articles(issue_id: str, article_ids) -> dict:
        ref = db.collection(COLLECTION).document(issue_id)
        snap = ref.get()
        if not snap.exists:
            return {"success": False, "message": "이슈를 찾을 수 없습니다."}
        cur = snap.to_dict()
        new_ids = [a for a in (article_ids or []) if a not in set(cur.get("article_ids") or [])]
        refs = [db.collection("articles").document(a) for a in new_ids]
        found = [{**d.to_dict(), "id": d.id} for d in db.get_all(refs) if d.exists] if refs else []
        patch = attach_articles(cur, found)
        # 기사 문서가 없는 id도 연결은 보존(관리자 수동 연결 호환)
        patch["article_ids"] += [a for a in new_ids if a not in set(patch["article_ids"])]
        ref.update({**patch, "updated_at": _now()})
        IssueService._refresh_digest(issue_id)
        return {"success": True, "message": "기사 연결 성공", "data": ref.get().to_dict()}

    @staticmethod
    def _refresh_digest(issue_id: str) -> None:
        try:
            from services.issue_digest_service import issue_digest_service
            issue_digest_service.refresh(issue_ids=[issue_id], press=False)
        except Exception as e:  # noqa: BLE001 — 관리자 쓰기 자체는 성공시킨다
            print(f"[issue digest refresh] {e!r}")


issue_service = IssueService()
