from utils.evidence_hash import evidence_hash


def test_order_independent():
    assert evidence_hash(["a", "b"]) == evidence_hash(["b", "a"])


def test_sources_change_hash():
    assert evidence_hash(["a"]) != evidence_hash(["a"], ["s1"])


def test_length_and_type():
    h = evidence_hash([])
    assert isinstance(h, str) and len(h) == 12
