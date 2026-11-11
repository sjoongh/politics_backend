"""의원 표결 → 이슈 역방향 매핑(순수). 법안 이슈 id는 결정적(issue_bill_{canonical})이라
존재 확인만 하면 되고, 같은 법안 소스에 수동 이슈가 연결돼 있으면 그쪽을 우선한다."""
from utils.bill_cluster import canonical_bill_id


def bill_issue_ids(votes) -> dict:
    out = {}
    for v in (votes or []):
        bid = v.get("bill_id")
        if bid:
            out[bid] = f"issue_bill_{canonical_bill_id(bid)}"
    return out


def attach_issue_ids(votes, existing_issue_ids, manual_by_bill) -> list:
    ids = bill_issue_ids(votes)
    out = []
    for v in (votes or []):
        bid = v.get("bill_id")
        issue_id = None
        if bid:
            if bid in (manual_by_bill or {}):
                issue_id = manual_by_bill[bid]
            elif ids.get(bid) in (existing_issue_ids or set()):
                issue_id = ids[bid]
        out.append({**v, "issue_id": issue_id})
    return out
