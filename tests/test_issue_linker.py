from utils.issue_linker import link_score, classify_link, best_issue, AUTO, LOW

ISSUE = {"id": "i1", "title": "노란봉투법 처리", "category": "정치",
         "keywords": ["노란봉투법", "노동"],
         "entities": {"bills": ["2120001"], "parties": ["국민의힘"]}}


def test_bill_id_exact_match_is_strong():
    s = {"entities": {"bills": ["2120001"], "parties": [], "people": []}, "title": "노란봉투법 표결"}
    assert link_score(s, ISSUE) >= AUTO


def test_keyword_only_is_weak():
    s = {"entities": {"bills": [], "parties": [], "people": []}, "title": "노동 관련 일반 기사"}
    assert link_score(s, ISSUE) < AUTO


def test_unrelated_is_zero():
    s = {"entities": {"bills": [], "parties": [], "people": []}, "title": "날씨 맑음"}
    assert link_score(s, ISSUE) == 0


def test_classify():
    assert classify_link(AUTO) == "auto"
    assert classify_link((AUTO + LOW) / 2) == "pending"
    assert classify_link(LOW - 1) is None


def test_best_issue_picks_highest():
    issues = [ISSUE, {"id": "i2", "title": "예산안", "keywords": ["예산"], "entities": {}}]
    s = {"entities": {"bills": ["2120001"], "parties": [], "people": []}, "title": "노란봉투법"}
    iss, score, status = best_issue(s, issues)
    assert iss["id"] == "i1" and status == "auto"
