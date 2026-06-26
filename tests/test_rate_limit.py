from utils.rate_limit import RateLimiter


def test_allows_within_limit():
    rl = RateLimiter(max_calls=3, window_sec=60)
    assert all(rl.allow("ip1", now=100 + i) for i in range(3))


def test_blocks_over_limit():
    rl = RateLimiter(max_calls=3, window_sec=60)
    for i in range(3):
        rl.allow("ip1", now=100 + i)
    assert rl.allow("ip1", now=103) is False        # 4번째 차단
    assert rl.allow("ip2", now=103) is True          # 다른 IP는 허용


def test_window_resets():
    rl = RateLimiter(max_calls=2, window_sec=60)
    rl.allow("ip1", now=100)
    rl.allow("ip1", now=101)
    assert rl.allow("ip1", now=102) is False
    assert rl.allow("ip1", now=200) is True          # 윈도우 지나면 다시 허용


def test_retry_after():
    rl = RateLimiter(max_calls=1, window_sec=60)
    rl.allow("ip1", now=100)
    assert rl.retry_after("ip1", now=130) == 30
