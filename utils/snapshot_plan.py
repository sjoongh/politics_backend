"""정적 스냅샷 계획(순수). 공개 GET 응답을 그대로 JSON 파일로 내보내 GitHub Pages에서 서빙한다.
프론트(politics_front src/hooks/snapshot.js)는 같은 canonical_key로 파일을 찾고, 없거나 오래되면 API로 폴백한다.
파일 모양: {"request": key, "generated_at": ISO8601, "body": <API 응답 본문 그대로>}"""
from datetime import datetime
from urllib.parse import urlencode

# every_h=0: 매 실행 갱신. 의원·검색 카탈로그는 자주 안 바뀌고 읽기가 커서(400·200건) 주기를 늘린다.
SNAPSHOTS = [
    {"file": "today.json", "path": "/api/today", "params": {}, "every_h": 0},
    {"file": "issues-rank-30.json", "path": "/api/issues", "params": {"v": 2, "sort": "rank", "limit": 30}, "every_h": 0},
    {"file": "issues-rank-50.json", "path": "/api/issues", "params": {"v": 2, "sort": "rank", "limit": 50}, "every_h": 0},
    {"file": "issues-catalog-200.json", "path": "/api/issues", "params": {"limit": 200}, "every_h": 6},
    {"file": "members-400.json", "path": "/api/members", "params": {"limit": 400}, "every_h": 24},
]


def canonical_key(path: str, params: dict) -> str:
    items = sorted((str(k), str(v)) for k, v in (params or {}).items())
    return path + ("?" + urlencode(items) if items else "")


def wrap(entry: dict, body: dict, now: datetime) -> dict:
    return {"request": canonical_key(entry["path"], entry["params"]),
            "generated_at": now.isoformat(), "body": body}


def _generated(prev):
    try:
        return datetime.fromisoformat(prev["generated_at"])
    except (TypeError, KeyError, ValueError):
        return None


def is_due(entry: dict, prev, now: datetime) -> bool:
    every = entry.get("every_h", 0)
    at = _generated(prev) if isinstance(prev, dict) else None
    if not every or at is None:
        return True
    return (now - at).total_seconds() >= every * 3600


def valid_body(status: int, body) -> bool:
    return status == 200 and isinstance(body, dict) and body.get("success") is True and "data" in body


def choose(entry: dict, prev, fresh_body, now: datetime):
    """새로 받은 정상 본문이 있으면 새 파일, 없으면 이전 정상본(last-known-good), 둘 다 없으면 None."""
    if fresh_body is not None:
        return wrap(entry, fresh_body, now)
    if isinstance(prev, dict) and _generated(prev) is not None and "body" in prev:
        return prev
    return None
