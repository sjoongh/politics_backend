"""source_item ↔ issue 연결 점수/판정 순수 로직 (테스트 대상).

법안번호 정확 일치를 최강 신호로, 정당/키워드/제목을 보조 신호로 점수화한다.
연결은 자동(auto)/검수(pending)/미연결 3단계로 분류해 '자동+사람 안전판'을 구현한다.
"""
AUTO = 10.0   # 이상이면 자동 연결
LOW = 4.0     # LOW~AUTO 미만이면 검수 큐(pending), 미만이면 미연결


def _bills(obj):
    return set((obj.get("entities") or {}).get("bills") or [])


def _parties(obj):
    return set((obj.get("entities") or {}).get("parties") or [])


def link_score(source_item, issue):
    s_bills = _bills(source_item)
    blob = (source_item.get("title") or "").lower()

    score = 0.0
    # 법안번호 정확 일치 = 강한 신호(같은 법안의 gov/bill/vote/news를 한 이슈로)
    if s_bills & _bills(issue):
        score += 12
    # 정당 일치
    if _parties(source_item) & _parties(issue):
        score += 3
    # 이슈 키워드가 소스 제목에 포함
    kw_hits = sum(1 for k in (issue.get("keywords") or []) if k and k.lower() in blob)
    score += kw_hits * 2.5
    # 이슈 제목 토큰이 소스 제목에 포함
    title_terms = [t for t in (issue.get("title") or "").lower().split() if len(t) >= 2]
    if any(t in blob for t in title_terms):
        score += 1.5
    return score


def classify_link(score):
    if score >= AUTO:
        return "auto"
    if score >= LOW:
        return "pending"
    return None


def best_issue(source_item, issues):
    """최고 점수 이슈와 점수/판정 반환. (issue|None, score, status)"""
    best, best_s = None, 0.0
    for iss in issues or []:
        s = link_score(source_item, iss)
        if s > best_s:
            best, best_s = iss, s
    return best, best_s, classify_link(best_s)
