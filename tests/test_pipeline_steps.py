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
