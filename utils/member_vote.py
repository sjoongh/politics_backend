"""의원 표결 기록 순수 로직 (테스트 대상).

열린국회 표결 행(RESULT_VOTE_MOD: 찬성/반대/기권/불참)을 의원별로 정리·집계한다.
codex: 발의보다 '주요 표결에서 어떤 선택을 했나'가 핵심 책임성 지표.
"""

_VALID = ("찬성", "반대", "기권", "불참")


def vote_label(result_vote_mod):
    r = (result_vote_mod or "").strip()
    for v in _VALID:
        if v in r:
            return v
    return "불참"   # 미표기/불참 처리


def vote_summary(votes):
    """[{vote}] → {찬성, 반대, 기권, 불참, total}."""
    counts = {v: 0 for v in _VALID}
    for x in (votes or []):
        counts[vote_label(x.get("vote"))] += 1
    return {**counts, "total": sum(counts.values())}


def merge_member_votes(existing, new_votes, cap=30):
    """기존 + 신규 표결을 bill_id로 dedup, 최신순 정렬, 상한 cap."""
    by_bill = {}
    for v in (existing or []) + (new_votes or []):
        bid = v.get("bill_id") or v.get("bill")
        if bid:
            by_bill[bid] = v   # 신규가 기존을 덮어씀(최신 결과 반영)
    merged = sorted(by_bill.values(), key=lambda v: str(v.get("date") or ""), reverse=True)
    return merged[:cap]
