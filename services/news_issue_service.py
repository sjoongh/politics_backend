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
            known = _member_names()
            raw = [d.to_dict() for d in db.collection("articles").limit(scan).stream()]
            # 엔티티 부착
            arts = []
            for a in raw:
                if not a.get("id"):
                    continue
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
                    cur = set(ref.get().to_dict().get("article_ids") or [])
                    ref.update({"article_ids": list(cur | set(c["article_ids"])), "updated_at": _now()})
                    attached += 1
                    continue

                # 결정적 key는 '토픽'(표현토큰 상위) 기준 — 이름 추출이 좋아져도 동일 이슈 유지(중복 방지).
                topic = " ".join(sorted(c["phrase_tokens"])[:4]) or rep or "|".join(sorted(names))
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
                    ref.update({k: doc[k] for k in
                                ("title", "summary", "keywords", "article_ids",
                                 "newsworthiness", "updated_at")})
                    updated += 1
                else:
                    doc.update({"started_at": _now(), "events": []})
                    ref.set(doc)
                    created += 1

            return {"success": True, "message": "뉴스 현안 이슈 생성",
                    "data": {"clusters": len(clusters), "created": created,
                             "updated": updated, "attached": attached}}
        except Exception as e:
            print(f"[generate_news_issues] {e!r}")
            return {"success": False, "message": "뉴스 이슈 생성 실패"}


news_issue_service = NewsIssueService()
