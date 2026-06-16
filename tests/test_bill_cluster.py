from utils.bill_cluster import cluster_by_bill, bill_id_of


def _item(id, type, bill_id, title="법안", status=""):
    s = {"id": id, "type": type, "title": title,
         "entities": {"bills": [bill_id] if bill_id else []}}
    if type == "assembly_bill":
        s["bill"] = {"bill_id": bill_id, "bill_name": title, "status": status}
    if type == "assembly_vote":
        s["vote"] = {"bill_id": bill_id, "result": status}
    return s


def test_bill_id_of_reads_all_locations():
    assert bill_id_of(_item("x", "assembly_bill", "B1")) == "B1"
    assert bill_id_of(_item("y", "assembly_vote", "B2")) == "B2"
    assert bill_id_of({"entities": {"bills": ["B3"]}}) == "B3"
    assert bill_id_of({"entities": {"bills": []}}) is None


def test_cluster_requires_significance():
    items = [
        _item("a", "assembly_bill", "B1", "노란봉투법", "계류"),   # 1종만 → 제외
        _item("b", "assembly_bill", "B2", "예산법", "계류"),
        _item("c", "assembly_vote", "B2", "예산법", "가결"),        # B2: bill+vote → 포함
    ]
    clusters = cluster_by_bill(items)
    ids = {c["bill_id"] for c in clusters}
    assert "B2" in ids and "B1" not in ids
    b2 = next(c for c in clusters if c["bill_id"] == "B2")
    assert b2["has_vote"] is True
    assert b2["bill_name"] == "예산법"
    assert set(b2["item_ids"]) == {"b", "c"}


def test_vote_alone_is_significant():
    items = [_item("v", "assembly_vote", "B9", "중요법", "가결")]
    clusters = cluster_by_bill(items)
    assert any(c["bill_id"] == "B9" for c in clusters)


def test_gov_plus_bill_significant():
    items = [
        {"id": "g", "type": "gov_policy", "title": "정부, 예산법 설명", "entities": {"bills": ["B5"]}},
        _item("bl", "assembly_bill", "B5", "예산법", "계류"),
    ]
    clusters = cluster_by_bill(items)
    assert any(c["bill_id"] == "B5" for c in clusters)
