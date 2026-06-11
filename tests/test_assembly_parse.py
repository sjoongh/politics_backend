from utils.assembly_parse import extract_rows


def test_extract_rows_ok():
    payload = {"svc": [
        {"head": [{"list_total_count": 1}, {"RESULT": {"CODE": "INFO-000"}}]},
        {"row": [{"A": 1}, {"A": 2}]},
    ]}
    assert extract_rows(payload, "svc") == [{"A": 1}, {"A": 2}]


def test_extract_rows_error_envelope():
    assert extract_rows({"RESULT": {"CODE": "ERROR-300", "MESSAGE": "x"}}, "svc") == []


def test_extract_rows_empty_or_malformed():
    assert extract_rows({}, "svc") == []
    assert extract_rows(None, "svc") == []
    assert extract_rows({"svc": [{"head": []}]}, "svc") == []
