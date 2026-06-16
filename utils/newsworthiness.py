"""이슈 사건성(newsworthiness) 점수 순수 로직 (테스트 대상).

'표결됨'이 아니라 갈등·연결·언론확산이 있는 것을 상위로. 절차적 대안법안은 감점.
"""
PROMOTE = 3.0   # 이슈 노출 최소 점수


def vote_contention(vote):
    """표결 갈등도 0~1. 만장일치=0, 찬반 접전·교차당 반대=높음."""
    if not vote:
        return 0.0
    yes, no = vote.get("yes", 0), vote.get("no", 0)
    total = yes + no + vote.get("abstain", 0)
    if total == 0:
        return 0.0
    closeness = 1 - abs(yes - no) / total          # 접전일수록 1
    pb = vote.get("party_breakdown") or {}
    has_yes = any(p.get("yes", 0) > 0 for p in pb.values())
    has_no = any(p.get("no", 0) > 0 for p in pb.values())
    cross = 1.0 if (has_yes and has_no) else 0.0    # 교차당 반대
    return round(min(1.0, 0.6 * closeness + 0.4 * cross), 3)


def issue_score(issue, source_items, article_count=0):
    types = {s.get("type") for s in (source_items or [])}
    contention = max((vote_contention(s.get("vote")) for s in (source_items or [])
                      if s.get("type") == "assembly_vote"), default=0.0)
    gov_connected = 1 if "gov_policy" in types else 0
    score = (contention * 4
             + min(len(types), 4) * 1.5
             + min(article_count, 5) * 1.2
             + gov_connected * 2)
    # 절차안 + 무뉴스 + 무갈등 → 감점(대안법안 도배 해소)
    if issue.get("procedural") and article_count == 0 and contention == 0:
        score -= 5
    return round(score, 2)
