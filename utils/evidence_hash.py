"""이슈 요약·입장 추출의 입력 근거 해시. 기사/소스 집합이 바뀌었을 때만 재생성하기 위한 키."""
import hashlib


def evidence_hash(article_ids, source_ids=()) -> str:
    raw = "|".join(sorted(str(a) for a in (article_ids or []))) + "#" + \
          "|".join(sorted(str(s) for s in (source_ids or [])))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
