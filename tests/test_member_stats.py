from utils.member_stats import classify_status, status_label, bill_stats


def test_classify_status():
    assert classify_status("원안가결") == "passed"
    assert classify_status("수정가결") == "passed"
    assert classify_status("대안반영폐기") == "reflected"   # 대안반영 우선
    assert classify_status("임기만료폐기") == "discarded"
    assert classify_status("철회") == "discarded"
    assert classify_status(None) == "pending"
    assert classify_status("") == "pending"


def test_status_label():
    assert status_label("원안가결") == "가결"
    assert status_label(None) == "심사중"


def test_bill_stats():
    bills = [{"PROC_RESULT": "원안가결"}, {"PROC_RESULT": "대안반영폐기"},
             {"PROC_RESULT": None}, {"PROC_RESULT": "임기만료폐기"}, {"PROC_RESULT": ""}]
    s = bill_stats(bills)
    assert s["total"] == 5
    assert s["passed"] == 1 and s["reflected"] == 1 and s["discarded"] == 1 and s["pending"] == 2
    assert s["enacted"] == 2  # 가결 + 대안반영
    assert s["enacted_rate"] == 40
