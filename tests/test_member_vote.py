from utils.member_vote import vote_label, vote_summary, merge_member_votes


def test_vote_label():
    assert vote_label("찬성") == "찬성"
    assert vote_label("반대") == "반대"
    assert vote_label("기권") == "기권"
    assert vote_label("") == "불참"
    assert vote_label(None) == "불참"


def test_vote_summary():
    votes = [{"vote": "찬성"}, {"vote": "찬성"}, {"vote": "반대"}, {"vote": ""}]
    s = vote_summary(votes)
    assert s["찬성"] == 2 and s["반대"] == 1 and s["불참"] == 1 and s["기권"] == 0
    assert s["total"] == 4


def test_merge_dedup_sort_cap():
    existing = [{"bill_id": "A", "vote": "찬성", "date": "20260101"}]
    new = [{"bill_id": "A", "vote": "반대", "date": "20260201"},   # 같은 법안 → 신규로 갱신
           {"bill_id": "B", "vote": "찬성", "date": "20260615"}]
    merged = merge_member_votes(existing, new, cap=10)
    assert len(merged) == 2                       # A dedup
    assert merged[0]["bill_id"] == "B"            # 최신순
    a = next(v for v in merged if v["bill_id"] == "A")
    assert a["vote"] == "반대"                     # 신규가 덮어씀


def test_merge_cap():
    votes = [{"bill_id": str(i), "date": f"2026{i:04d}"} for i in range(50)]
    assert len(merge_member_votes([], votes, cap=30)) == 30
