"""TTL 캐시 테스트."""
import threading
from utils.ttl_cache import TTLCache


def test_set_get():
    c = TTLCache(maxsize=10, ttl=100)
    c.set("a", 1)
    assert c.get("a") == 1
    assert c.get("missing") is None


def test_ttl_expiry():
    c = TTLCache(maxsize=10, ttl=100)
    c.set("a", 1, ttl=0)  # 즉시 만료
    assert c.get("a") is None


def test_lru_eviction():
    c = TTLCache(maxsize=2, ttl=100)
    c.set("a", 1)
    c.set("b", 2)
    c.get("a")          # a를 최근 사용으로
    c.set("c", 3)       # 가장 오래된(b) 제거
    assert c.get("a") == 1
    assert c.get("c") == 3
    assert c.get("b") is None


def test_thread_safety_no_crash():
    c = TTLCache(maxsize=50, ttl=100)

    def worker(n):
        for i in range(200):
            c.set(f"{n}-{i}", i)
            c.get(f"{n}-{i}")

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(c._store) <= 50  # maxsize 유지
