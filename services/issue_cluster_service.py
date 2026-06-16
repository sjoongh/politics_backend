"""법안 기준 이슈 자동 생성: 같은 법안의 source_items를 한 이슈로 묶는다.

- significance(표결 또는 소스 2종↑) 클러스터만 이슈화(codex)
- 수동 우선: 같은 법안의 수동 이슈가 있으면 자동 생성 않고 그 이슈에 링크
- 자동 이슈는 결정적 id(issue_bill_{canonical}) + auto_generated 메타로 충돌 회피
- 제목=법안명 그대로, 요약=규칙 기반(AI 미사용 — 쿼터 절약/정확성)
"""
from datetime import datetime, timezone
from firebase.firebase_config import db
from utils.bill_cluster import cluster_by_bill


def _now():
    return datetime.now(timezone.utc).isoformat()


def _cluster_bill_set(items):
    """클러스터 내 모든 식별자(PRC + 의안번호) 합집합 — 향후 정부/뉴스 매칭용."""
    out = []
    for it in items:
        for b in (it.get("entities") or {}).get("bills") or []:
            if b and b not in out:
                out.append(b)
    return out


class IssueClusterService:
    async def generate_bill_issues(self, scan: int = 500) -> dict:
        try:
            # 법안 관련 소스만 스캔
            src = []
            for t in ("assembly_bill", "assembly_vote", "gov_policy"):
                src += [d.to_dict() for d in
                        db.collection("source_items").where("type", "==", t).limit(scan).stream()]
            clusters = cluster_by_bill(src)

            created = updated = linked = 0
            for c in clusters:
                cbid = c["canonical_id"]
                items = [s for s in src if s.get("id") in set(c["item_ids"])]
                bill_set = _cluster_bill_set(items) or [c["bill_id"]]

                # 수동 이슈 충돌 검사(같은 법안의 사람 생성 이슈 우선).
                # limit 없이 전부 본 뒤 수동 이슈를 찾는다(자동 이슈가 먼저 잡혀 수동우선이 깨지는 것 방지 — codex).
                issue_id = None
                for b in bill_set:
                    for h in db.collection("issues").where("entities.bills", "array_contains", b).stream():
                        if not h.to_dict().get("auto_generated"):
                            issue_id = h.id
                            break
                    if issue_id:
                        break

                if issue_id is None:
                    # 결정적 자동 이슈 id(멱등)
                    issue_id = f"issue_bill_{cbid}"
                    ref = db.collection("issues").document(issue_id)
                    exists = ref.get().exists
                    doc = {
                        "id": issue_id,
                        "title": c["bill_name"],
                        "summary": f"‘{c['bill_name']}’ 관련 정부·국회 1차 소스를 묶은 자동 생성 이슈입니다.",
                        "status": c["status"] or "진행중",
                        "category": "정치",
                        "keywords": [c["bill_name"]],
                        "entities": {"bills": bill_set, "parties": [], "people": []},
                        "auto_generated": True,
                        "auto_key": f"bill:{cbid}",
                        "updated_at": _now(),
                    }
                    if exists:
                        # 갱신 시 entities/메타는 보존하고 변동 필드만(향후 엔티티 보강 유실 방지 — codex)
                        ref.update({k: doc[k] for k in
                                    ("title", "summary", "status", "keywords", "updated_at")})
                        updated += 1
                    else:
                        doc.update({"started_at": _now(), "events": [], "article_ids": []})
                        ref.set(doc)
                        created += 1

                # 클러스터 소스들을 이슈에 연결
                for sid in c["item_ids"]:
                    db.collection("source_items").document(sid).update(
                        {"issue_id": issue_id, "link_status": "auto", "updated_at": _now()})
                    linked += 1

            return {"success": True, "message": "법안 이슈 자동생성",
                    "data": {"clusters": len(clusters), "created": created,
                             "updated": updated, "linked": linked}}
        except Exception as e:
            print(f"[generate_bill_issues] {e!r}")
            return {"success": False, "message": "법안 이슈 자동생성 실패"}


issue_cluster_service = IssueClusterService()
