"""매체 성향 매핑 순수 로직 (firebase 비의존, 테스트 대상).
라벨은 통용되는 분류를 출발점으로 한 참고값이며 설정 가능."""

# 성향: left(진보) / right(보수) / center(중도·통신사·지상파) / foreign(외신) / official(공식)
_LEANING = {
    "left": ["한겨레", "경향", "오마이뉴스", "프레시안", "민중"],
    "right": ["동아", "조선", "중앙", "문화일보", "세계일보", "한국경제", "서울경제", "매일경제"],
    "center": ["연합뉴스", "연합뉴스TV", "뉴시스", "뉴스1", "YTN", "SBS", "KBS", "MBC", "서울신문", "JTBC", "한국일보"],
    "foreign": ["BBC", "VOA", "NHK", "CNN", "로이터", "AFP", "외신"],
    "official": ["대통령실", "정책", "부처", "정부", "브리핑", "청와대"],
}


def source_leaning(source) -> str:
    """매체명으로 성향 반환. 부분 일치 허용. 미상은 'unknown'."""
    if not source:
        return "unknown"
    for leaning, names in _LEANING.items():
        if any(name in source for name in names):
            return leaning
    return "unknown"


def bias_breakdown(articles) -> dict:
    """기사 목록의 성향별 집계 + blindspot(정치 진영 한쪽만 보도) 계산."""
    counts = {"left": 0, "center": 0, "right": 0, "foreign": 0, "official": 0, "unknown": 0}
    for a in (articles or []):
        counts[source_leaning(a.get("source", ""))] += 1
    total = sum(counts.values())
    blindspot = None
    if counts["left"] > 0 and counts["right"] == 0:
        blindspot = "right"
    elif counts["right"] > 0 and counts["left"] == 0:
        blindspot = "left"
    return {"counts": counts, "total": total, "blindspot": blindspot}
