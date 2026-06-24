"""의원 발의 법안 처리상태 분류·집계 순수 로직 (테스트 대상).

codex: '발의 수'가 아니라 '처리 흐름(통과/대안반영/폐기/심사중)'을 보여준다.
"""

# 처리상태 → 분류. 우선순위 순으로 검사.
def classify_status(proc_result):
    r = proc_result or ""
    if "대안반영" in r:
        return "reflected"        # 대안에 반영(사실상 입법 성과)
    if "가결" in r:
        return "passed"           # 원안/수정 가결
    if "폐기" in r or "철회" in r or "부결" in r:
        return "discarded"        # 폐기/철회/부결
    return "pending"              # 심사중/계류(빈값 포함)


_LABEL = {"passed": "가결", "reflected": "대안반영", "discarded": "폐기/철회", "pending": "심사중"}


def status_label(proc_result):
    return _LABEL[classify_status(proc_result)]


def bill_stats(bills):
    """발의 법안 목록 → 처리 흐름 집계."""
    counts = {"passed": 0, "reflected": 0, "discarded": 0, "pending": 0}
    for b in (bills or []):
        counts[classify_status(b.get("PROC_RESULT") or b.get("status"))] += 1
    total = sum(counts.values())
    # 입법 성과 = 가결 + 대안반영
    enacted = counts["passed"] + counts["reflected"]
    return {
        "total": total,
        "enacted": enacted,
        "enacted_rate": round(enacted / total * 100) if total else 0,
        **counts,
    }
