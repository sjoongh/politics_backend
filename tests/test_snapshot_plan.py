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
                 "fresh_for_s": 3 * 3600, "body": {"success": True, "data": {}}}


def test_wrap_tells_clients_how_long_the_file_stays_fresh():
    hourly = wrap({"path": "/api/today", "params": {}, "every_h": 0}, {"success": True, "data": 1}, NOW)
    daily = wrap({"path": "/api/members", "params": {"limit": 400}, "every_h": 24}, {"success": True, "data": 1}, NOW)
    assert hourly["fresh_for_s"] == 3 * 3600       # 매시 수집 + 누락 여유
    assert daily["fresh_for_s"] == 25 * 3600       # 갱신 주기 + 1시간


def test_partial_export_never_deletes_a_deployed_file():
    from utils.snapshot_plan import safe_to_deploy
    allf = [s["file"] for s in SNAPSHOTS]
    assert safe_to_deploy(allf, prev_manifest_status=200, prev_manifest={"files": {}})
    # today.json이 배포돼 있었는데 이번에 못 만들었으면 배포하지 않는다(기존 Pages 유지)
    missing_today = [f for f in allf if f != "today.json"]
    assert not safe_to_deploy(missing_today, 200, {"files": {"today.json": {}}})
    # 이전 manifest를 못 읽으면(네트워크) 하나라도 빠지면 배포하지 않는다
    assert not safe_to_deploy(missing_today, 0, None)
    # 처음 배포(manifest 404)면 일부만 있어도 배포한다
    assert safe_to_deploy(missing_today, 404, None)
    assert not safe_to_deploy([], 404, None)
