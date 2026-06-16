from utils.source_item import (
    make_source_id, strip_html, extract_entities, normalize_gov_policy, normalize_bill,
)


def test_make_source_id_stable_and_dedup():
    a = make_source_id("government", "https://korea.kr/x?newsId=1&call_from=rsslink")
    b = make_source_id("government", "https://korea.kr/x?newsId=1")  # 추적 파라미터 달라도 동일
    assert a == b
    assert isinstance(a, str) and len(a) == 16


def test_strip_html():
    assert strip_html("<a href='x'>한-EU</a> 협정") == "한-EU 협정"


def test_extract_entities_bill_and_party():
    e = extract_entities("국민의힘이 발의한 노란봉투법(의안번호 2120001) 본회의 통과")
    assert "국민의힘" in e["parties"]
    assert "2120001" in e["bills"]


def test_normalize_gov_policy():
    item = {"title": "정책 발표",
            "link": "https://korea.kr/news/policyNewsView.do?newsId=148966556&call_from=rsslink",
            "description": "<a href='x'>정부가 발표</a>", "date": "2026-06-15T09:13:00Z"}
    s = normalize_gov_policy(item)
    assert s["type"] == "gov_policy" and s["actor_type"] == "government"
    assert s["source_bias"] == "official"
    assert s["url"].startswith("https://korea.kr")
    assert s["published_at"] == "2026-06-15T09:13:00Z"
    assert s["id"]


def test_normalize_bill():
    bill = {"BILL_ID": "PRC_X1", "BILL_NAME": "노란봉투법", "PROPOSER": "홍길동,김철수",
            "PROC_RESULT": "원안가결", "PROPOSE_DT": "2026-06-10"}
    s = normalize_bill(bill)
    assert s["type"] == "assembly_bill" and s["actor_type"] == "assembly"
    assert s["bill"]["bill_id"] == "PRC_X1"
    assert "PRC_X1" in s["entities"]["bills"]
    assert s["position"] == "propose"
