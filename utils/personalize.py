"""개인화 추천 순수 로직 (firebase/AI 비의존, 테스트 대상).

- build_profile: 명시적 관심사 + 북마크에서 뽑은 암묵 키워드 → 프로필
- pick_reason: 추천 사유 문장(설명가능성 — codex)
- diversify: 점수순을 유지하되 카테고리 연속/출처 편중을 깨 다양성 강제(필터버블 방어)
"""
from collections import Counter


def normalize_terms(terms):
    """소문자화 + 공백정리 + 중복제거(순서 보존)."""
    seen, out = set(), []
    for t in terms or []:
        s = " ".join(str(t).lower().split())
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def implicit_keywords(bookmark_articles, top_n=8, min_count=1):
    """북마크한 기사들의 keywords 빈도 상위 N개(암묵 관심)."""
    c = Counter()
    for a in bookmark_articles or []:
        for k in (a.get("keywords") or []):
            s = " ".join(str(k).lower().split())
            if s:
                c[s] += 1
    return [k for k, n in c.most_common(top_n) if n >= min_count]


def build_profile(interests, bookmark_articles):
    """명시적 관심사 + 암묵 키워드를 합쳐 랭킹용 프로필 생성.
    반환: (parsed_like dict, explicit:list, implicit:list) — 순서 보존(추천사유 결정성)."""
    explicit = normalize_terms(interests)
    implicit = [k for k in implicit_keywords(bookmark_articles) if k not in set(explicit)]
    keywords = explicit + implicit
    parsed = {
        "keywords": keywords,
        "category": None,
        "entities": [],
        "parties": [],
        "date_preset": "recent",  # 개인화 피드는 최신성 가중
    }
    return parsed, explicit, implicit


def _blob(a):
    return (
        (a.get("title") or "") + " " +
        (a.get("ai_summary") or "") + " " +
        " ".join(str(k) for k in (a.get("keywords") or []))
    ).lower()


def pick_reason(article, explicit_set, implicit_set):
    """이 기사가 추천된 이유 한 줄(설명가능성)."""
    blob = _blob(article)
    for kw in explicit_set:
        if kw and kw in blob:
            return f"관심사 ‘{kw}’ 와 관련"
    for kw in implicit_set:
        if kw and kw in blob:
            return f"자주 저장한 주제 ‘{kw}’"
    return "최근 주요 정치뉴스"


def diversify(items, limit, max_per_source=3, max_category_run=2):
    """점수순 items를 받아 다양성을 강제한 최종 리스트 반환.
    - 동일 출처는 max_per_source개로 제한
    - 같은 카테고리가 max_category_run회 연속되면 다른 카테고리를 먼저 끼워넣음
    """
    pool = []
    src_count = {}
    for it in items:
        s = it.get("source") or "?"
        if src_count.get(s, 0) >= max_per_source:
            continue
        src_count[s] = src_count.get(s, 0) + 1
        pool.append(it)

    out = []
    run_cat, run_len = None, 0
    while pool and len(out) < limit:
        idx = 0
        if run_cat is not None and run_len >= max_category_run:
            # 연속 한도 도달 → 다른 카테고리 후보를 우선 탐색
            alt = next((i for i, it in enumerate(pool) if (it.get("category") or "") != run_cat), None)
            if alt is not None:
                idx = alt
        it = pool.pop(idx)
        cat = it.get("category") or ""
        if cat == run_cat:
            run_len += 1
        else:
            run_cat, run_len = cat, 1
        out.append(it)
    return out
