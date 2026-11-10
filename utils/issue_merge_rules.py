"""병합된 이슈 id 해석 (firebase 비의존, 테스트 대상).

흡수된 이슈 문서는 `merged_into`로 남는 문서를 가리킨다. 공유 링크·상세·판은
모두 이 함수로 정본 id를 구한다. 순환·과도한 체인은 마지막 유효 id에서 멈춘다.
"""
from typing import Callable, Optional


def follow_merge(issue_id: str, lookup: Callable[[str], Optional[dict]], max_hops: int = 3) -> str:
    current = issue_id
    seen = {current}
    for _ in range(max_hops):
        doc = lookup(current)
        nxt = (doc or {}).get("merged_into")
        if not nxt or nxt in seen:
            return current
        seen.add(nxt)
        current = nxt
    return current
