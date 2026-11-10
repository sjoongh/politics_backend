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
    async def generate_news_issues(self, days: int = 7, scan: int = 400) -> dict:
        try:
            from google.cloud import firestore as _fs
            known = _member_names()
            # 최근 기사 우선(라이브 현안 전제) + 문서 id 보강
            raw = [{**d.to_dict(), "id": d.id} for d in db.collection("articles")
                   .order_by("published_at", direction=_fs.Query.DESCENDING).limit(scan).stream()]
            arts = []
            for a in raw:
                a["entities"] = extract_entities(a.get("title"), a.get("ai_summary"), known)
                arts.append(a)

            clusters = cluster_articles(arts, window_days=days, min_articles=2, min_sources=2)
            by_id = {a["id"]: a for a in arts}

            created = updated = attached = 0
            existing = [{**d.to_dict(), "id": d.id} for d in db.collection("issues").stream()]

            for c in clusters:
                members = [by_id[i] for i in c["article_ids"]]
                rep = _rep_phrase(members)
                names = c["names"]
                ptoks = set(c["phrase_tokens"])

                # 기존 이슈(수동/법안)와 강한 겹침이면 거기에 기사 attach(중복 이슈 방지)
                target = None
                for iss in existing:
                    if iss.get("auto_key", "").startswith("news:"):
                        continue
                    hay = (iss.get("title", "") + " " + " ".join(iss.get("keywords") or []))
                    if (any(n in hay for n in names) and (ptoks & set(re.split(r"\s+", hay)))) \
                            or (rep and rep in hay):
                        target = iss["id"]
                        break

                if target:
                    ref = db.collection("issues").document(target)
                    cur_doc = ref.get().to_dict() or {}
                    ref.update({**attach_articles(cur_doc, members), "updated_at": _now()})
                    attached += 1
                    continue

                # 결정적 key는 빈도기반 대표 phrase(정규화) 기준 — 사전순 토큰보다 안정적(codex).
                from utils.news_entities import normalize_phrase
                topic = normalize_phrase(rep) or "|".join(sorted(names)) or " ".join(sorted(c["phrase_tokens"])[:3])
                key = hashlib.sha1(topic.encode()).hexdigest()[:14]
                issue_id = f"issue_news_{key}"
                ref = db.collection("issues").document(issue_id)
                exists = ref.get().exists
                doc = {
                    "id": issue_id,
                    "title": _title(names, rep),
                    "summary": f"여러 매체가 보도한 현안입니다(관련 기사 {c['count']}건·출처 {c['sources']}곳).",
                    "status": "진행중",
                    "category": "정치",
                    "keywords": [k for k in ([rep] + names) if k][:6],
                    "entities": {"bills": [], "parties": [], "people": names},
                    "article_ids": c["article_ids"],
                    "newsworthiness": round(2 + c["count"] * 0.8 + c["sources"] * 0.6, 2),
                    "auto_generated": True,
                    "auto_key": f"news:{key}",
                    "updated_at": _now(),
                }
                if exists:
                    # article_ids는 합집합으로(과거 연결 기사 유실 방지 — codex) + article_meta 갱신
                    cur_doc = ref.get().to_dict() or {}
                    patch = {k: doc[k] for k in
                             ("title", "summary", "keywords", "newsworthiness", "updated_at")}
                    patch.update(attach_articles(cur_doc, members))
                    ref.update(patch)
                    updated += 1
                else:
                    doc.update({"started_at": _now(), "events": []})
                    doc.update(attach_articles({"article_ids": []}, members))
                    ref.set(doc)
                    created += 1

            return {"success": True, "message": "뉴스 현안 이슈 생성",
                    "data": {"clusters": len(clusters), "created": created,
                             "updated": updated, "attached": attached}}
        except Exception as e:
            print(f"[generate_news_issues] {e!r}")
            return {"success": False, "message": "뉴스 이슈 생성 실패"}


    async def summarize_pending_issues(self, limit: int = 10) -> dict:
        """자동 이슈의 요약을 AI 사건요약으로(예산 안에서). 대상: 미요약이거나 근거가 크게 바뀐 이슈.
        예산 거부(budget)·쿼터(http_429)가 나오면 즉시 중단한다."""
        import asyncio
        from utils.gemini_rest import summarize_issue
        from utils.collect_config import ai_throttle_seconds
        from utils.evidence_hash import evidence_hash
        try:
            throttle = ai_throttle_seconds()
            autos = []
            for d in db.collection("issues").stream():
                iss = {**d.to_dict(), "id": d.id}
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
