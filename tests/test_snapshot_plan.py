from datetime import datetime, timedelta, timezone

from utils.snapshot_plan import SNAPSHOTS, canonical_key, choose, is_due, valid_body, wrap

NOW = datetime(2026, 11, 11, 9, 0, tzinfo=timezone.utc)


def test_canonical_key_sorts_params_and_stringifies():
    assert canonical_key("/api/issues", {"v": 2, "sort": "rank", "limit": 30}) == "/api/issues?limit=30&sort=rank&v=2"
    assert canonical_key("/api/today", {}) == "/api/today"


def test_canonical_key_matches_frontend_table():
    # politics_front src/hooks/snapshot.js의 SNAPSHOT_FILES와 같은 키여야 어댑터가 찾는다
    keys = {canonical_key(s["path"], s["params"]): s["file"] for s in SNAPSHOTS}
    assert keys == {
        "/api/today": "today.json",
        "/api/issues?limit=30&sort=rank&v=2": "issues-rank-30.json",
        "/api/issues?limit=50&sort=rank&v=2": "issues-rank-50.json",
        "/api/issues?limit=200": "issues-catalog-200.json",
        "/api/members?limit=400": "members-400.json",
    }


def test_due_every_run_or_after_interval():
    hourly = {"every_h": 0}
    daily = {"every_h": 24}
    assert is_due(hourly, prev=None, now=NOW)
    assert is_due(hourly, prev=wrap({"path": "/x", "params": {}}, {"success": True, "data": 1}, NOW), now=NOW)
    fresh = wrap({"path": "/x", "params": {}}, {"success": True, "data": 1}, NOW - timedelta(hours=3))
    assert not is_due(daily, prev=fresh, now=NOW)
    old = wrap({"path": "/x", "params": {}}, {"success": True, "data": 1}, NOW - timedelta(hours=25))
    assert is_due(daily, prev=old, now=NOW)
    assert is_due(daily, prev={"broken": True}, now=NOW)


def test_valid_body_requires_success_and_data():
    assert valid_body(200, {"success": True, "data": []})
    assert not valid_body(200, {"success": False, "message": "429"})
    assert not valid_body(500, {"success": True, "data": []})
    assert not valid_body(200, None)
    assert not valid_body(200, {"success": True})


def test_choose_keeps_last_good_copy_when_fetch_fails():
    entry = {"path": "/api/today", "params": {}}
    prev = wrap(entry, {"success": True, "data": {"edition": None}}, NOW - timedelta(hours=1))
    assert choose(entry, prev, None, NOW) == prev                      # 새로 못 받으면 이전 정상본 유지
    new = choose(entry, prev, {"success": True, "data": {"edition": {"date": "2026-11-11"}}}, NOW)
    assert new["generated_at"] == NOW.isoformat() and new["request"] == "/api/today"
    assert choose(entry, None, None, NOW) is None                      # 둘 다 없으면 파일을 만들지 않음


def test_wrap_records_request_and_time():
    w = wrap({"path": "/api/members", "params": {"limit": 400}}, {"success": True, "data": {}}, NOW)
    assert w == {"request": "/api/members?limit=400", "generated_at": NOW.isoformat(),
                 "body": {"success": True, "data": {}}}
