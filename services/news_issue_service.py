"""뉴스 기반 현안 이슈 자동 생성.

최근 기사를 엔티티/표현으로 클러스터링 → 여러 출처가 다룬 것만 이슈로 승격.
제목/요약은 규칙 기반(AI 미사용). 결정적 id로 멱등, 기존 이슈와 중복 회피.
"""
import re
import hashlib
from datetime import datetime, timezone
from collections import Counter
from firebase.firebase_config import db
from utils.news_entities import extract_entities
from utils.news_cluster import cluster_articles
from utils.article_meta import attach_articles
from utils.issue_merge import top_person, clean_title, should_merge
from utils.fallback_summary import fallback_summary
from utils.issue_merge_rules import follow_merge


def _now():
    return datetime.now(timezone.utc).isoformat()


def _member_names():
    names = set()
    for d in db.collection("members").limit(500).stream():
        n = d.to_dict().get("name")
        if n and len(n) >= 2:
            names.add(n)
    return names


def _rep_phrase(members):
    """클러스터 대표 표현(가장 흔하고 긴 따옴표 표현)."""
    cnt = Counter()
    for m in members:
        for p in (m.get("entities") or {}).get("phrases") or []:
            cnt[p] += 1
    if not cnt:
        return ""
    # 빈도 우선, 동률이면 긴 것
    return sorted(cnt.items(), key=lambda kv: (kv[1], len(kv[0])), reverse=True)[0][0]


def _title(names, rep_phrase):
    if names and rep_phrase:
        return f"{names[0]} ‘{rep_phrase}’"
    if rep_phrase:
        return f"‘{rep_phrase}’ 논란"
    if names:
        return f"{names[0]} 관련 현안"
    return "정치 현안"


class NewsIssueService:
    async def generate_news_issues(self, days: int = 7, scan: int = 400, ctx=None) -> dict:
        """ctx(PipelineContext)가 있으면 기사·이슈·의원명을 공유 로더에서 받아 읽기를 아낀다."""
        try:
            from google.cloud import firestore as _fs
            now_dt = datetime.now(timezone.utc)
            known = ctx.member_names() if ctx else _member_names()
            if ctx:
                raw = ctx.articles(scan)
            else:
                raw = [{**d.to_dict(), "id": d.id} for d in db.collection("articles")
                       .order_by("published_at", direction=_fs.Query.DESCENDING).limit(scan).stream()]
            arts = []
            for a in raw:
                a = dict(a)
                a["entities"] = extract_entities(a.get("title"), a.get("ai_summary"), known)
                arts.append(a)

            clusters = cluster_articles(arts, window_days=days, min_articles=2, min_sources=2)
            by_id = {a["id"]: a for a in arts}

            created = updated = attached = 0
            touched = []
            if ctx:
                existing = ctx.active_issues()
            else:
                existing = [{**d.to_dict(), "id": d.id} for d in db.collection("issues").stream()
                            if d.to_dict().get("active") is not False]

            for c in clusters:
                members = [by_id[i] for i in c["article_ids"]]
                rep = _rep_phrase(members)
                names = c["names"]
                ptoks = set(c["phrase_tokens"])
                person = top_person(members) or (names[0] if names else None)
                people = ([person] if person else []) + [n for n in names if n != person]
                cluster = {"article_ids": set(c["article_ids"]), "person": person, "phrases": [rep] if rep else []}

                # 기존 이슈 대조: 수동/법안은 제목·키워드 겹침, 뉴스 이슈는 should_merge(오병합 방지 기준)
                target = None
                for iss in existing:
                    if str(iss.get("auto_key") or "").startswith("news:"):
                        if should_merge(cluster, iss, now_dt):
                            target = iss
                            break
                        continue
                    hay = (iss.get("title", "") + " " + " ".join(iss.get("keywords") or []))
                    if (any(n in hay for n in names) and (ptoks & set(re.split(r"\s+", hay)))) \
                            or (rep and rep in hay):
                        target = iss
                        break

                # 결정적 id 문서가 이미 흡수됐으면(merged_into) 생존 문서를 대상으로 삼는다(I6)
                if target is None:
                    from utils.news_entities import normalize_phrase as _np
                    _topic = _np(rep) or "|".join(sorted(names)) or " ".join(sorted(c["phrase_tokens"])[:3])
                    _did = f"issue_news_{hashlib.sha1(_topic.encode()).hexdigest()[:14]}"
                    _snap = db.collection("issues").document(_did).get()
                    if _snap.exists and (_snap.to_dict() or {}).get("merged_into"):
                        _sid = follow_merge(_did, lambda i: (lambda s_: s_.to_dict() if s_.exists else None)(
                            db.collection("issues").document(i).get()))
                        if _sid != _did:
                            target = next((i for i in existing if i["id"] == _sid), None) or {"id": _sid}

                if target:
                    ref = db.collection("issues").document(target["id"])
                    cur_doc = ref.get().to_dict() or {}
                    patch = {**attach_articles(cur_doc, members), "updated_at": _now()}
                    if cur_doc.get("auto_generated") and not cur_doc.get("ai_summarized"):
                        patch["summary"] = fallback_summary({**cur_doc, **patch}, by_id)
                    ref.update(patch)
                    target.update(patch)
                    touched.append(target["id"])
                    if ctx:
                        ctx.mark_issue_changed(target["id"])
                    attached += 1
                    continue

                # 결정적 key는 빈도기반 대표 phrase(정규화) 기준 — 사전순 토큰보다 안정적(codex).
                from utils.news_entities import normalize_phrase
                topic = normalize_phrase(rep) or "|".join(sorted(names)) or " ".join(sorted(c["phrase_tokens"])[:3])
                key = hashlib.sha1(topic.encode()).hexdigest()[:14]
                issue_id = f"issue_news_{key}"
                ref = db.collection("issues").document(issue_id)
                snap = ref.get()
                doc = {
                    "id": issue_id,
                    "title": clean_title(person, rep),
                    "status": "진행중",
                    "category": "정치",
                    "keywords": [k for k in ([rep] + people) if k][:6],
                    "entities": {"bills": [], "parties": [], "people": people},
                    "newsworthiness": round(2 + c["count"] * 0.8 + c["sources"] * 0.6, 2),
                    "auto_generated": True,
                    "auto_key": f"news:{key}",
                    "active": True,
                    "updated_at": _now(),
                }
                if snap.exists:
                    cur_doc = snap.to_dict() or {}
                    patch = {k: doc[k] for k in ("title", "keywords", "newsworthiness", "updated_at")}
                    patch.update(attach_articles(cur_doc, members))
                    if not cur_doc.get("ai_summarized"):
                        patch["summary"] = fallback_summary({**cur_doc, **patch, "auto_key": doc["auto_key"]}, by_id)
                    if cur_doc.get("active") is None:
                        patch["active"] = True
                    ref.update(patch)
                    updated += 1
                else:
                    doc.update({"started_at": _now(), "events": [], "ai_summarized": False})
                    doc.update(attach_articles({"article_ids": []}, members))
                    doc["summary"] = fallback_summary(doc, by_id)
                    ref.set(doc)
                    existing.append(doc)
                    created += 1
                touched.append(issue_id)
                if ctx:
                    ctx.mark_issue_changed(issue_id)

            return {"success": True, "message": "뉴스 현안 이슈 생성",
                    "data": {"clusters": len(clusters), "created": created,
                             "updated": updated, "attached": attached, "issue_ids": touched}}
        except Exception as e:
            print(f"[generate_news_issues] {e!r}")
            return {"success": False, "message": "뉴스 이슈 생성 실패"}


    async def summarize_pending_issues(self, limit: int = 10, ctx=None) -> dict:
        """자동 이슈의 요약을 AI 사건요약으로(예산 안에서). 대상: 미요약이거나 근거가 크게 바뀐 이슈.
        예산 거부(budget)·쿼터(http_429)가 나오면 즉시 중단한다."""
        import asyncio
        from utils.gemini_rest import summarize_issue
        from utils.collect_config import ai_throttle_seconds
        from utils.evidence_hash import evidence_hash
        try:
            throttle = ai_throttle_seconds()
            autos = []
            pool = ctx.active_issues() if ctx is not None else [{**d.to_dict(), "id": d.id} for d in db.collection("issues").stream()]
            for iss in pool:
                if not iss.get("auto_generated") or iss.get("active") is False:
                    continue
                ids = iss.get("article_ids") or []
                h = evidence_hash(ids)
                if not iss.get("ai_summarized"):
                    autos.append(iss)
                elif h != iss.get("evidence_hash") and len(ids) >= int(iss.get("evidence_n") or 0) + 5:
                    autos.append(iss)
            autos.sort(key=lambda x: ((x.get("digest") or {}).get("rank") or x.get("newsworthiness") or 0),
                       reverse=True)
            done = 0
            stop = None
            if ctx is not None:
                autos = [a for a in autos if a["id"] in set(ctx.changed_issue_ids)] or autos
            for iss in autos[:limit]:
                ids = (iss.get("article_ids") or [])[:8]
                refs = [db.collection("articles").document(a) for a in ids]
                arts = [a.to_dict() for a in db.get_all(refs) if a.exists] if refs else []
                snippets = [(a.get("title") or "") + " — " + (a.get("ai_summary") or "")[:120] for a in arts]
                if not snippets:
                    continue
                summary, reason = await summarize_issue(iss.get("title"), snippets)
                if not summary:
                    if reason in ("budget", "http_429"):
                        stop = reason
                        break
                    continue  # 일시 실패는 다음 run 재시도
                db.collection("issues").document(iss["id"]).update(
                    {"summary": summary, "ai_summarized": True,
                     "evidence_hash": evidence_hash(iss.get("article_ids") or []),
                     "evidence_n": len(iss.get("article_ids") or []), "updated_at": _now()})
                done += 1
                if throttle:
                    await asyncio.sleep(throttle)
            return {"success": True, "message": "AI 사건요약",
                    "data": {"summarized": done, "scanned": len(autos[:limit]), "stopped": stop}}
        except Exception as e:
            print(f"[summarize_pending_issues] {e!r}")
            return {"success": False, "message": "AI 사건요약 실패"}


news_issue_service = NewsIssueService()
