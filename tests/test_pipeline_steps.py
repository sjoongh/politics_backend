from utils.pipeline_steps import select_steps, is_heavy_hour, LIGHT, HEAVY, DAILY


def test_light_only_off_hours():
    assert select_steps(1) == LIGHT and select_steps(4) == LIGHT


def test_heavy_every_three_hours():
    assert is_heavy_hour(0) and is_heavy_hour(21) and not is_heavy_hour(22)
    assert select_steps(6) == LIGHT + HEAVY


def test_force_and_only():
    assert select_steps(1, heavy=True) == LIGHT + HEAVY
    assert select_steps(1, only=["crosslink", "bogus"]) == ["crosslink"]


def test_daily_member_steps_once_a_day():
    assert select_steps(3) == LIGHT + HEAVY + DAILY
    assert select_steps(6) == LIGHT + HEAVY
    assert select_steps(1, daily=True) == LIGHT + DAILY


def test_heavy_due_by_elapsed_time_not_clock_hour():
    from utils.pipeline_steps import heavy_due
    from datetime import datetime, timezone
    now = datetime(2026, 11, 11, 1, 30, tzinfo=timezone.utc)          # KST 10:30 (3의 배수 아님)
    assert heavy_due(None, now)                                         # 기록 없음 → 실행
    assert heavy_due("2026-11-10T22:00:00+00:00", now)                 # 3.5h 경과 → 실행
    assert not heavy_due("2026-11-11T00:00:00+00:00", now)             # 1.5h 경과 → 생략
    assert heavy_due("garbage", now)                                    # 깨진 기록 → 실행


def test_daily_due_once_per_kst_day():
    from utils.pipeline_steps import daily_due
    from datetime import datetime, timezone
    now = datetime(2026, 11, 11, 1, 30, tzinfo=timezone.utc)           # KST 11-11
    assert daily_due(None, now)
    assert not daily_due("2026-11-11", now)
    assert daily_due("2026-11-10", now)
