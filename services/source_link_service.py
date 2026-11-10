"""source_item ↔ issue 연결: 자동(고신뢰) + 검수 큐(애매) 하이브리드."""
from datetime import datetime, timezone
from firebase.firebase_config import db
from utils.issue_linker import best_issue
from utils.article_meta import attach_articles
from utils.crosslink_match import article_matches_issue
from utils.source_links import add_link, has_link, is_rejected, news_issue_link_score


def _now():
    return datetime.now(timezone.utc).isoformat()


class SourceLinkService:
    async def link_unlinked(self, limit: int = 200, ctx=None) -> dict:
        """미연결(link_status='new') 소스를 이슈에 자동 연결하거나 검수 큐로."""
        try:
            # 문서 id 주입(필드에 id 없는 seed 데이터에서 KeyError 방지 — codex)
            issues = ctx.active_issues() if ctx else [
                {**d.to_dict(), "id": d.id} for d in db.collection("issues").stream()
                if d.to_dict().get("active") is not False]
            n_auto = n_pending = 0
            touched = []
            if ctx:
                class _Doc:  # ctx 소스를 doc처럼 다루는 얇은 어댑터
                    def __init__(self, s):
                        self.id = s["id"]
                        self._s = s
                        self.reference = db.collection("source_items").document(s["id"])
                    def to_dict(self):
                        return dict(self._s)
                docs = [_Doc(s) for s in ctx.recent_sources(14) if s.get("link_status") == "new"][:limit]
            else:
                docs = db.collection("source_items").where("link_status", "==", "new").limit(limit).stream()
            for doc in docs:
                s = doc.to_dict()
                iss, score, status = best_issue(s, issues)
                if status in ("auto", "pending") and iss and not is_rejected(s, iss["id"]):
                    linked = add_link({**s, "id": doc.id}, iss["id"], status, score, "linker", _now())
                    doc.reference.update({**{k: linked[k] for k in ("links", "issue_ids", "issue_id", "link_status")},
                                          "updated_at": _now()})
                    if status == "auto":
                        n_auto += 1
                        touched.append(iss["id"])
                        if ctx:
                            ctx.mark_issue_changed(iss["id"])
                    else:
                        n_pending += 1
                # 점수 미달은 'new' 유지(다음 이슈 생성 후 재시도 가능)
            return {"success": True, "message": "연결 완료",
                    "data": {"auto": n_auto, "pending": n_pending, "issue_ids": list(dict.fromkeys(touched))}}
        except Exception as e:
            print(f"[link_unlinked] {e!r}")
            return {"success": False, "message": "연결 실패"}

    async def list_pending(self, limit: int = 50) -> dict:
        try:
            docs = db.collection("source_items").where("link_status", "==", "pending").limit(limit).stream()
            items = [d.to_dict() for d in docs]
            return {"success": True, "message": "검수 대기", "data": {"items": items, "count": len(items)}}
        except Exception as e:
            print(f"[list_pending] {e!r}")
            return {"success": False, "message": "검수 목록 조회 실패"}

    async def review(self, source_id: str, action: str, issue_id: str = None) -> dict:
        """관리자 검수(관계 단위): confirm(승인) / reject(거부). issue_id 없이 reject하면 모든 관계 거부."""
        ref = db.collection("source_items").document(source_id)
        snap = ref.get()
        if not snap.exists:
            return {"success": False, "message": "소스를 찾을 수 없습니다."}
        s = {**snap.to_dict(), "id": source_id}
        if action == "confirm":
            target = issue_id or s.get("issue_id")
            if not target:
                return {"success": False, "message": "issue_id가 필요합니다."}
            if not db.collection("issues").document(target).get().exists:
                return {"success": False, "message": "해당 이슈가 존재하지 않습니다."}
            linked = add_link(s, target, "confirmed", 100.0, "review", _now())
        elif action == "reject":
            linked = s
            targets = [issue_id] if issue_id else ([l.get("issue_id") for l in (s.get("links") or [])] or [s.get("issue_id")])
            for t in [t for t in targets if t]:
                linked = add_link(linked, t, "rejected", 0, "review", _now())
            if not (linked.get("links") or []):
                linked = {**linked, "issue_id": None, "link_status": "rejected", "issue_ids": []}
        else:
            return {"success": False, "message": "action은 confirm|reject"}
        ref.update({**{k: linked.get(k) for k in ("links", "issue_ids", "issue_id", "link_status")}, "updated_at": _now()})
        return {"success": True, "message": "검수 반영"}

    async def crosslink(self, scan_articles: int = 300, ctx=None) -> dict:
        """이슈에 gov/news를 교차연결.
        - 뉴스: 이슈 law_name(있으면) 또는 제목/키워드가 기사 제목·요약에 등장하면 article_ids에 추가
        - 정부: gov_policy의 의안번호(entities.bills)가 이슈와 겹치거나 law_name이 제목에 등장하면 연결
        의안번호 직접 일치는 강한 신호, 법률명 등장은 보조(길이 3+만)."""
        try:
            from google.cloud import firestore as _fs
            if ctx:
                issues = ctx.active_issues()
                arts = ctx.articles(scan_articles)
                govs = [dict(g) for g in ctx.recent_sources(14) if g.get("type") == "gov_policy"]
            else:
                issues = [{**d.to_dict(), "id": d.id} for d in db.collection("issues").stream()
                          if d.to_dict().get("active") is not False]
                arts = [{**d.to_dict(), "id": d.id} for d in db.collection("articles")
                        .order_by("published_at", direction=_fs.Query.DESCENDING)
                        .limit(scan_articles).stream()]
                govs = [{**d.to_dict(), "id": d.id} for d in
                        db.collection("source_items").where("type", "==", "gov_policy").limit(500).stream()]
            touched = []

            news_linked = gov_linked = 0
            for iss in issues:
                # 매칭어: 법률명/키워드 중 길이 3+ 만(짧은 일반어 오연결 방지 — codex).
                # 제목 첫단어 휴리스틱은 '국민/정부' 등 대량 오연결 위험이라 제거.
                # 기사 매칭 규칙은 utils/crosslink_match(뉴스 이슈: 인용구 기준, 인명 단독 불가)
                bills = set((iss.get("entities") or {}).get("bills") or [])

                # 뉴스 매칭 → article_ids 추가
                existing = set(iss.get("article_ids") or [])
                add = []
                for a in arts:
                    aid = a.get("id")
                    blob = (a.get("title", "") + " " + a.get("ai_summary", ""))
                    if aid and aid not in existing and article_matches_issue(blob, iss):
                        add.append(a)
                    if len(add) >= 12:
                        break
                if add:
                    patch = attach_articles(iss, add)
                    db.collection("issues").document(iss["id"]).update({**patch, "updated_at": _now()})
                    iss.update(patch)
                    news_linked += len(add)
                    touched.append(iss["id"])
                    if ctx:
                        ctx.mark_issue_changed(iss["id"])

                # 정부 소스 매칭 → issue 연결. 의안번호 일치=강함, 법률명(4+) 등장=보조.
                # 한 번 연결된 gov는 로컬 상태도 갱신해 다른 이슈가 덮어쓰지 않게(codex).
                law = iss.get("law_name") or ""
                for g in govs:
                    if has_link(g, iss["id"]) or (not g.get("links") and g.get("link_status") in ("auto", "confirmed", "rejected")):
                        continue
                    g_bills = set((g.get("entities") or {}).get("bills") or [])
                    gtitle = g.get("title", "")
                    if (bills & g_bills) or (len(law) >= 4 and law in gtitle):
                        linked = add_link(g, iss["id"], "auto", 12.0, "bill_or_law", _now())
                        db.collection("source_items").document(g["id"]).update(
                            {**{k: linked[k] for k in ("links", "issue_ids", "issue_id", "link_status")}, "updated_at": _now()})
                        g.update(linked)
                        gov_linked += 1
                        touched.append(iss["id"])
                        if ctx:
                            ctx.mark_issue_changed(iss["id"])
            return {"success": True, "message": "교차연결",
                    "data": {"news": news_linked, "gov": gov_linked, "issue_ids": list(dict.fromkeys(touched))}}
        except Exception as e:
            print(f"[crosslink] {e!r}")
            return {"success": False, "message": "교차연결 실패"}


    async def link_news_issues(self, days: int = 14, limit: int = 300, dry_run: bool = False, ctx=None) -> dict:
        """최근 N일 소스(법안·표결·정부)를 뉴스 이슈에 추가 연결(다대다).
        정확 일치(law_name/bill_name 전체 포함)만 auto, 제안자∩인물은 pending. dry_run이면 후보만 반환."""
        try:
            from datetime import timedelta
            if ctx:
                issues = [i for i in ctx.active_issues() if str(i.get("auto_key") or "").startswith("news:")]
                sources = ctx.recent_sources(days)
            else:
                issues = [{**d.to_dict(), "id": d.id} for d in db.collection("issues").stream()
                          if d.to_dict().get("active") is not False
                          and str(d.to_dict().get("auto_key") or "").startswith("news:")]
                cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
                from google.cloud import firestore as _fs
                sources = [{**d.to_dict(), "id": d.id} for d in db.collection("source_items")
                           .where("published_at", ">=", cutoff)
                           .order_by("published_at", direction=_fs.Query.DESCENDING).limit(limit).stream()]
            n_auto = n_pending = 0
            cands, touched = [], []
            for iss in issues:
                blob = " ".join([iss.get("title") or "", iss.get("summary") or ""] + list(iss.get("keywords") or []))
                people = (iss.get("entities") or {}).get("people") or []
                for src in sources:
                    if has_link(src, iss["id"]) or is_rejected(src, iss["id"]):
                        continue
                    score, status = news_issue_link_score(src, blob, people)
                    if not status:
                        continue
                    cands.append({"source": src.get("title"), "type": src.get("type"), "issue": iss.get("title"),
                                  "score": score, "status": status})
                    if dry_run:
                        continue
                    linked = add_link(src, iss["id"], status, score, "news_exact" if status == "auto" else "proposer", _now())
                    db.collection("source_items").document(src["id"]).update(
                        {**{k: linked[k] for k in ("links", "issue_ids", "issue_id", "link_status")}, "updated_at": _now()})
                    src.update(linked)
                    if status == "auto":
                        n_auto += 1
                        touched.append(iss["id"])
                        if ctx:
                            ctx.mark_issue_changed(iss["id"])
                    else:
                        n_pending += 1
            return {"success": True, "message": "뉴스 이슈 소스 연결",
                    "data": {"auto": n_auto, "pending": n_pending, "scanned_sources": len(sources),
                             "candidates": cands[:20] if dry_run else len(cands),
                             "issue_ids": list(dict.fromkeys(touched))}}
        except Exception as e:
            print(f"[link_news_issues] {e!r}")
            return {"success": False, "message": "뉴스 이슈 소스 연결 실패"}


source_link_service = SourceLinkService()
