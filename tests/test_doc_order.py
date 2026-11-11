from utils.doc_order import order_by_ids


def test_orders_and_skips_missing():
    docs = [{"id": "b"}, {"id": "a"}]
    assert [d["id"] for d in order_by_ids(docs, ["a", "x", "b"])] == ["a", "b"]


def test_custom_key():
    docs = [{"k": "2"}, {"k": "1"}]
    assert [d["k"] for d in order_by_ids(docs, ["1", "2"], key="k")] == ["1", "2"]
