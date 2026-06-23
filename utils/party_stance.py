"""이슈에 연결된 기사에서 정당별 입장을 도출하는 순수 로직 (테스트 대상).

정당 공식 보도자료 RSS가 없어, 기사(=정당 발언이 잦음)를 정당별로 묶어 보여준다.
정치편향 우려를 피하려 '여/야'가 아니라 정당명 그대로 표기한다.
"""
_PARTIES = ["더불어민주당", "국민의힘", "조국혁신당", "개혁신당", "진보당",
            "정의당", "기본소득당", "사회민주당", "민주당", "국힘"]
# 약칭 → 정식 명칭(기사마다 표기가 달라 같은 정당이 따로 잡히는 것 방지)
_CANON = {"민주당": "더불어민주당", "국힘": "국민의힘"}


def detect_parties(text):
    t = text or ""
    found = [_CANON.get(p, p) for p in _PARTIES if p in t]
    seen, out = set(), []
    for p in found:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def group_by_party(articles):
    """기사 목록 → [{party, count, articles[{title, source, source_url}]}] (기사 수 내림차순)."""
    groups = {}
    for a in (articles or []):
        blob = (a.get("title") or "") + " " + (a.get("ai_summary") or "")
        for p in detect_parties(blob):
            groups.setdefault(p, []).append({
                "title": a.get("title"),
                "source": a.get("source"),
                "source_url": a.get("source_url"),
            })
    out = [{"party": p, "count": len(v), "articles": v[:5]} for p, v in groups.items()]
    out.sort(key=lambda g: g["count"], reverse=True)
    return out
