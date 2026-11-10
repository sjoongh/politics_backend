"""source_item ↔ issue 다대다 관계(순수).

정본은 `links: [{issue_id, status, score, reason, at}]`. `issue_ids`는 status∈{auto,confirmed}인
조회용 파생 배열, `issue_id`/`link_status`는 첫 승인 관계(없으면 첫 관계)의 미러(구 코드 호환).
거절(rejected)된 관계는 자동 연결로 되살리지 않는다.
"""
APPROVED = ("auto", "confirmed")


def _links(source: dict) -> list:
    return list(source.get("links") or [])


def has_link(source: dict, issue_id: str) -> bool:
    return any(l.get("issue_id") == issue_id for l in _links(source))


def is_rejected(source: dict, issue_id: str) -> bool:
    return any(l.get("issue_id") == issue_id and l.get("status") == "rejected" for l in _links(source))


def issue_ids_of(source: dict) -> list:
    out = []
    for l in _links(source):
        if l.get("status") in APPROVED and l.get("issue_id") not in out:
            out.append(l["issue_id"])
    return out


def _mirror(source: dict) -> dict:
    links = _links(source)
    first = next((l for l in links if l.get("status") in APPROVED), links[0] if links else None)
    source["issue_ids"] = issue_ids_of(source)
    source["issue_id"] = first["issue_id"] if first else None
    source["link_status"] = first["status"] if first else "new"
    return source


def add_link(source: dict, issue_id: str, status: str, score: float, reason: str, at: str) -> dict:
    src = dict(source)
    links = _links(src)
    if status != "rejected" and is_rejected(src, issue_id) and status in ("auto", "pending"):
        src["links"] = links
        return _mirror(src)
    links = [l for l in links if l.get("issue_id") != issue_id]
    links.append({"issue_id": issue_id, "status": status, "score": float(score or 0), "reason": reason, "at": at})
    src["links"] = links
    return _mirror(src)


def news_issue_link_score(source: dict, issue_blob: str, people) -> tuple:
    """뉴스 이슈용 점수. 정확 일치만 auto, 약한 신호는 pending."""
    blob = issue_blob or ""
    law = source.get("law_name") or ""
    bill = source.get("bill") or {}
    name = bill.get("bill_name") or ""
    if (len(law) >= 4 and law in blob) or (len(name) >= 4 and name in blob):
        return (12.0, "auto")
    proposers = set(bill.get("proposers") or [])
    if proposers and proposers & set(people or []):
        return (5.0, "pending")
    return (0, None)
