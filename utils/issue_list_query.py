"""이슈 목록 v2 쿼리 계획(순수). 정렬 3종 × 단일 필터, 항상 active == True.
Firestore 복합 인덱스는 firestore.indexes.json에 이 조합대로 선언한다."""
SORT_FIELDS = {
    "rank": "digest.rank",
    "updated": "digest.last_activity_at",
    "media": "digest.counts.media",
}
BOOL_FILTERS = {"has_official": "digest.has_official", "has_vote": "digest.has_vote", "has_gov": "digest.has_gov"}


def build_query_plan(sort, filter_) -> dict:
    where = [("active", "==", True)]
    f = (filter_ or "").strip()
    if f in BOOL_FILTERS:
        where.append((BOOL_FILTERS[f], "==", True))
    elif f.startswith("status:") and f[len("status:"):]:
        where.append(("status", "==", f[len("status:"):]))
    return {"order": SORT_FIELDS.get(sort or "rank", SORT_FIELDS["rank"]), "where": where}
