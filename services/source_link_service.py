"""source_item ↔ issue 연결: 자동(고신뢰) + 검수 큐(애매) 하이브리드."""
from datetime import datetime, timezone
from firebase.firebase_config import db
from utils.issue_linker import best_issue


def _now():
    return datetime.now(timezone.utc).isoformat()


class SourceLinkService:
    async def link_unlinked(self, limit: int = 200) -> dict:
        """미연결(link_status='new') 소스를 이슈에 자동 연결하거나 검수 큐로."""
        try:
            # 문서 id 주입(필드에 id 없는 seed 데이터에서 KeyError 방지 — codex)
            issues = [{**d.to_dict(), "id": d.id} for d in db.collection("issues").stream()]
            n_auto = n_pending = 0
            docs = db.collection("source_items").where("link_status", "==", "new").limit(limit).stream()
            for doc in docs:
                s = doc.to_dict()
                iss, score, status = best_issue(s, issues)
                if status == "auto" and iss:
                    doc.reference.update({"issue_id": iss["id"], "link_status": "auto", "updated_at": _now()})
                    n_auto += 1
                elif status == "pending" and iss:
                    doc.reference.update({"issue_id": iss["id"], "link_status": "pending", "updated_at": _now()})
                    n_pending += 1
                # 점수 미달은 'new' 유지(다음 이슈 생성 후 재시도 가능)
            return {"success": True, "message": "연결 완료", "data": {"auto": n_auto, "pending": n_pending}}
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
        """관리자 검수: confirm(승인) / reject(거부)."""
        ref = db.collection("source_items").document(source_id)
        if not ref.get().exists:
            return {"success": False, "message": "소스를 찾을 수 없습니다."}
        if action == "confirm":
            patch = {"link_status": "confirmed", "updated_at": _now()}
            if issue_id:
                # 존재하는 이슈만 연결(오타·임의 ID로 깨진 연결 방지 — codex)
                if not db.collection("issues").document(issue_id).get().exists:
                    return {"success": False, "message": "해당 이슈가 존재하지 않습니다."}
                patch["issue_id"] = issue_id
            ref.update(patch)
        elif action == "reject":
            ref.update({"link_status": "rejected", "issue_id": None, "updated_at": _now()})
        else:
            return {"success": False, "message": "action은 confirm|reject"}
        return {"success": True, "message": "검수 반영"}


    async def crosslink(self, scan_articles: int = 300) -> dict:
        """이슈에 gov/news를 교차연결.
        - 뉴스: 이슈 law_name(있으면) 또는 제목/키워드가 기사 제목·요약에 등장하면 article_ids에 추가
        - 정부: gov_policy의 의안번호(entities.bills)가 이슈와 겹치거나 law_name이 제목에 등장하면 연결
        의안번호 직접 일치는 강한 신호, 법률명 등장은 보조(길이 3+만)."""
        try:
            from google.cloud import firestore as _fs
            issues = [{**d.to_dict(), "id": d.id} for d in db.collection("issues").stream()]
            arts = [d.to_dict() for d in db.collection("articles")
                    .order_by("published_at", direction=_fs.Query.DESCENDING)
                    .limit(scan_articles).stream()]
            govs = [{**d.to_dict(), "_ref": d.reference} for d in
                    db.collection("source_items").where("type", "==", "gov_policy").limit(500).stream()]

            news_linked = gov_linked = 0
            for iss in issues:
                # 매칭어: 법률명/키워드 중 길이 3+ 만(짧은 일반어 오연결 방지 — codex).
                # 제목 첫단어 휴리스틱은 '국민/정부' 등 대량 오연결 위험이라 제거.
                terms = set()
                if iss.get("law_name") and len(iss["law_name"]) >= 3:
                    terms.add(iss["law_name"])
                for k in (iss.get("keywords") or []):
                    if k and len(k) >= 3:
                        terms.add(k)
                if not terms:
                    continue
                bills = set((iss.get("entities") or {}).get("bills") or [])

                # 뉴스 매칭 → article_ids 추가
                existing = set(iss.get("article_ids") or [])
                add_ids = []
                for a in arts:
                    aid = a.get("id")
                    blob = (a.get("title", "") + " " + a.get("ai_summary", ""))
                    if aid and aid not in existing and any(t in blob for t in terms):
                        add_ids.append(aid)
                    if len(add_ids) >= 12:
                        break
                if add_ids:
                    db.collection("issues").document(iss["id"]).update(
                        {"article_ids": list(existing | set(add_ids)), "updated_at": _now()})
                    news_linked += len(add_ids)

                # 정부 소스 매칭 → issue 연결. 의안번호 일치=강함, 법률명(4+) 등장=보조.
                # 한 번 연결된 gov는 로컬 상태도 갱신해 다른 이슈가 덮어쓰지 않게(codex).
                law = iss.get("law_name") or ""
                for g in govs:
                    if g.get("link_status") in ("auto", "confirmed", "rejected"):
                        continue
                    g_bills = set((g.get("entities") or {}).get("bills") or [])
                    gtitle = g.get("title", "")
                    if (bills & g_bills) or (len(law) >= 4 and law in gtitle):
                        g["_ref"].update({"issue_id": iss["id"], "link_status": "auto", "updated_at": _now()})
                        g["link_status"] = "auto"
                        gov_linked += 1
            return {"success": True, "message": "교차연결", "data": {"news": news_linked, "gov": gov_linked}}
        except Exception as e:
            print(f"[crosslink] {e!r}")
            return {"success": False, "message": "교차연결 실패"}


source_link_service = SourceLinkService()
