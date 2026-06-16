"""법안 기준 클러스터링 순수 로직 (firebase 비의존, 테스트 대상).

bill_id를 키로 같은 법안의 source_items를 묶는다. significance(표결 존재 또는
소스 2종 이상)인 클러스터만 이슈화 대상으로 본다(법안 단독은 제외 — codex).
"""
import re


def canonical_bill_id(bill_id):
    """법안 식별자 정규화(포맷 흔들림으로 인한 중복 이슈 방지 — codex).
    영숫자/언더스코어만 남기고 대문자화. 예: '2201234호' → '2201234'."""
    if not bill_id:
        return ""
    return re.sub(r"[^0-9A-Za-z_]", "", str(bill_id)).upper()


def bill_id_of(item):
    """source_item에서 대표 bill_id 추출(entities.bills 우선, bill/vote 보조)."""
    bills = (item.get("entities") or {}).get("bills") or []
    if bills:
        return bills[0]
    for key in ("bill", "vote"):
        sub = item.get(key) or {}
        if sub.get("bill_id"):
            return sub["bill_id"]
    return None


def _pick_name(items):
    for i in items:
        if i.get("type") == "assembly_bill" and i.get("title"):
            return i["title"]
    for i in items:
        if i.get("bill") and i["bill"].get("bill_name"):
            return i["bill"]["bill_name"]
    return (items[0].get("title") or "").replace("표결: ", "")


def _pick_status(items):
    # 표결 결과 우선, 없으면 법안 상태
    for i in items:
        if i.get("type") == "assembly_vote" and (i.get("vote") or {}).get("result"):
            return i["vote"]["result"]
    for i in items:
        if i.get("type") == "assembly_bill" and (i.get("bill") or {}).get("status"):
            return i["bill"]["status"]
    return "진행중"


def cluster_by_bill(source_items, min_types=2):
    """bill_id별로 묶어 significance 클러스터만 반환.
    significance = 표결 포함 OR 서로 다른 소스 타입 min_types개 이상."""
    by_bill = {}
    for s in source_items or []:
        bid = bill_id_of(s)
        cbid = canonical_bill_id(bid)
        if not cbid:            # 빈 식별자 제외(issue_bill_ 충돌 방지 — codex)
            continue
        by_bill.setdefault(cbid, {"raw": bid, "items": []})
        by_bill[cbid]["items"].append(s)

    clusters = []
    for cbid, grp in by_bill.items():
        items = grp["items"]
        types = {i.get("type") for i in items}
        has_vote = "assembly_vote" in types
        if not (has_vote or len(types) >= min_types):
            continue  # 법안 단독 등 약한 클러스터 제외
        clusters.append({
            "bill_id": grp["raw"],
            "canonical_id": cbid,
            "bill_name": _pick_name(items),
            "status": _pick_status(items),
            "types": sorted(types),
            "has_vote": has_vote,
            "item_ids": [i.get("id") for i in items if i.get("id")],
        })
    return clusters
