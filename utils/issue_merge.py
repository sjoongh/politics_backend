"""뉴스 이슈 중복 방지·병합 판정 (firebase 비의존, 테스트 대상).

오병합 0건이 중복 0건보다 우선한다. 병합 조건(모두 만족):
  같은 대표 인물  AND  기존 이슈가 최근 14일 안에 활동  AND
  (인용구(4자↑) 포함 관계 OR 인용구 토큰 Jaccard ≥ 0.5)

기사 겹침 비율은 쓰지 않는다. 라이브 dry-run(2026-11-10)에서 인명 단독 크로스링크로 오염된
기사 집합 때문에 서로 다른 사건(김민석 '호남 반도체' vs '한중 관계')이 0.85 겹침으로 잡혔다.
"""
import re
from collections import Counter
from datetime import datetime, timedelta, timezone

STALE_DAYS = 14
PHRASE_MIN = 4
TOKEN_JACCARD_MIN = 0.5
_STOP = {"관련", "논란", "현안", "의원", "대표", "정부", "국회", "오늘", "내일", "이번", "지난"}


def top_person(members):
    cnt = Counter()
    for m in (members or []):
        for p in ((m.get("entities") or {}).get("people") or []):
            if p:
                cnt[p] += 1
    if not cnt:
        return None
    return sorted(cnt.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)[0][0]


def clean_title(name, phrase) -> str:
    phrase = (phrase or "").strip()
    if name and phrase:
        phrase = re.sub(re.escape(name), "", phrase).strip(" ,·")
        phrase = re.sub(r"\s{2,}", " ", phrase).strip()
        if phrase:
            return f"{name} ‘{phrase}’"
        return f"{name} 관련 현안"
    if phrase:
        return f"‘{phrase}’ 논란"
    if name:
        return f"{name} 관련 현안"
    return "정치 현안"


def _parse(s):
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00").replace(" ", "T"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _last_activity(issue):
    return _parse((issue.get("digest") or {}).get("last_activity_at")) or _parse(issue.get("updated_at"))


def _issue_person(issue):
    people = (issue.get("entities") or {}).get("people") or []
    return people[0] if people else None


def _issue_phrases(issue):
    return [k for k in (issue.get("keywords") or []) if k] + ([issue.get("title")] if issue.get("title") else [])


def _phrase_contains(p_a, p_b) -> bool:
    for a in p_a:
        for b in p_b:
            if len(a) >= PHRASE_MIN and len(b) >= PHRASE_MIN and (a in b or b in a):
                return True
    return False


def _tokens(phrases) -> set:
    out = set()
    for p in (phrases or []):
        for t in re.split(r"[\s,·‘’'\"…]+", p or ""):
            t = t.strip()
            if len(t) >= 2 and t not in _STOP:
                out.add(t)
    return out


def _token_jaccard(p_a, p_b) -> float:
    a, b = _tokens(p_a), _tokens(p_b)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def should_merge(cluster: dict, issue: dict, now: datetime, stale_days: int | None = STALE_DAYS) -> bool:
    """stale_days=None은 활동 기간 조건을 끈다(오래된 중복을 한 번 정리하는 수동 실행 전용)."""
    person = cluster.get("person")
    if not person or person not in ((issue.get("entities") or {}).get("people") or []):
        return False
    if stale_days is not None:
        last = _last_activity(issue)
        if last is None or now - last > timedelta(days=stale_days):
            return False
    phrases = list(cluster.get("phrases") or [])
    issue_phrases = [k for k in (issue.get("keywords") or []) if k and k != person]
    if _phrase_contains(phrases, issue_phrases):
        return True
    return _token_jaccard(phrases, issue_phrases) >= TOKEN_JACCARD_MIN


def merge_plan(issues, now: datetime, stale_days: int | None = STALE_DAYS):
    """(흡수될 id, 남을 id) 쌍. 뉴스 이슈끼리만, 오래된 것이 남고, 한 문서는 한 번만."""
    news = [i for i in (issues or []) if str(i.get("auto_key") or "").startswith("news:") and not i.get("merged_into")]
    news.sort(key=lambda i: str(i.get("started_at") or i.get("updated_at") or ""))
    taken, pairs = set(), []
    for idx, keep in enumerate(news):
        if keep["id"] in taken:
            continue
        for other in news[idx + 1:]:
            if other["id"] in taken:
                continue
            cluster = {"article_ids": set(other.get("article_ids") or []), "person": _issue_person(other),
                       "phrases": [k for k in (other.get("keywords") or []) if k and k != _issue_person(other)]}
            if should_merge(cluster, keep, now, stale_days):
                pairs.append((other["id"], keep["id"]))
                taken.add(other["id"])
    return pairs
