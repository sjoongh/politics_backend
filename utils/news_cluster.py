"""뉴스 기사 클러스터링 순수 로직 (테스트 대상).

같은 현안 = 공유 인물 + 공유 표현토큰(또는 공유 전체 phrase) + 시간창 이내.
'여러 출처가 다룸'(min_sources)을 뉴스가치 신호로 승격.
"""
import re
from datetime import datetime, timezone, timedelta


def _ts(a):
    v = a.get("published_at") or a.get("created_at") or ""
    s = str(v).replace(" ", "T").replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


# 프레이밍/범용 토큰 — 이걸로만 연결되면 엉뚱한 사건이 합쳐짐(codex). 링크 신호에서 제외.
_STOP_TOKENS = {"논란", "입장", "발표", "촉구", "요구", "비판", "반발", "공방", "의혹",
                "사퇴", "규탄", "강조", "주장", "우려", "지적", "전망", "예고", "결정",
                "국민", "정부", "여당", "야당", "대통령"}


def _phrase_tokens(phrases):
    """phrase를 길이 2+ 토큰으로(공유 토큰 매칭용). 범용 프레이밍 토큰은 제외."""
    toks = set()
    for p in phrases or []:
        for t in re.split(r"\s+", p):
            if len(t) >= 2 and t not in _STOP_TOKENS:
                toks.add(t)
    return toks


def _signals(a):
    e = a.get("entities") or {}
    return {
        "names": set(e.get("names") or []),
        "ptokens": _phrase_tokens(e.get("phrases")),
        "phrases": {p for p in (e.get("phrases") or []) if len(p) >= 4},
    }


def _linked(s1, s2):
    """두 기사가 같은 현안인가: (공유 인물 AND 공유 표현토큰) 또는 공유 전체 phrase."""
    if s1["names"] & s2["names"] and s1["ptokens"] & s2["ptokens"]:
        return True
    if s1["phrases"] & s2["phrases"]:
        return True
    return False


def cluster_articles(articles, window_days=7, min_articles=2, min_sources=2):
    arts = [a for a in (articles or []) if _ts(a)]
    sig = {a["id"]: _signals(a) for a in arts if a.get("id")}
    arts = [a for a in arts if a.get("id")]

    # union-find
    parent = {a["id"]: a["id"] for a in arts}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        parent[find(a)] = find(b)

    for i in range(len(arts)):
        for j in range(i + 1, len(arts)):
            a, b = arts[i], arts[j]
            dt = abs((_ts(a) - _ts(b)).days)
            if dt <= window_days and _linked(sig[a["id"]], sig[b["id"]]):
                union(a["id"], b["id"])

    groups = {}
    by_id = {a["id"]: a for a in arts}
    for a in arts:
        groups.setdefault(find(a["id"]), []).append(a["id"])

    clusters = []
    for root, ids in groups.items():
        if len(ids) < min_articles:
            continue
        members = [by_id[i] for i in ids]
        sources = {m.get("source") for m in members if m.get("source")}  # None 출처 제외(codex)
        if len(sources) < min_sources:
            continue
        names, ptoks = set(), set()
        for m in members:
            names |= sig[m["id"]]["names"]
            ptoks |= sig[m["id"]]["ptokens"]
        ts_list = [_ts(m) for m in members]
        clusters.append({
            "article_ids": ids,
            "count": len(ids),
            "sources": len(sources),
            "names": sorted(names),
            "phrase_tokens": sorted(ptoks),
            "start": min(ts_list).isoformat(),
            "end": max(ts_list).isoformat(),
        })
    clusters.sort(key=lambda c: (c["count"], c["sources"]), reverse=True)
    return clusters
