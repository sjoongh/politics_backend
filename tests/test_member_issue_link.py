from utils.member_issue_link import bill_issue_ids, attach_issue_ids
from utils.bill_cluster import canonical_bill_id

V = [{"bill_id": "PRC_X1", "bill": "국민연금법", "vote": "찬성"}, {"bill": "no id", "vote": "반대"}]


def test_ids():
    assert bill_issue_ids(V) == {"PRC_X1": "issue_bill_" + canonical_bill_id("PRC_X1")}


def test_manual_preferred():
    out = attach_issue_ids(V, {"issue_bill_" + canonical_bill_id("PRC_X1")}, {"PRC_X1": "manual1"})
    assert out[0]["issue_id"] == "manual1" and out[1]["issue_id"] is None


def test_bill_issue_when_exists():
    out = attach_issue_ids(V, {"issue_bill_" + canonical_bill_id("PRC_X1")}, {})
    assert out[0]["issue_id"] == "issue_bill_" + canonical_bill_id("PRC_X1")


def test_none_when_absent():
    assert attach_issue_ids(V, set(), {})[0]["issue_id"] is None
