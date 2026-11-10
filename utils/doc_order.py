"""get_all 결과를 요청한 id 순서로 재정렬(없는 id는 건너뜀)."""


def order_by_ids(docs, ids, key="id"):
    by = {d.get(key): d for d in (docs or []) if d.get(key) is not None}
    return [by[i] for i in (ids or []) if i in by]
