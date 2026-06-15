"""아주 작은 인메모리 TTL 캐시 (순수, 테스트 가능).

서버리스(Vercel)에서 warm 인스턴스가 유지되는 동안 동일/인기 질의의 Gemini
재호출을 막아 무료 쿼터를 아낀다. cold start 시 비워지는 건 의도된 한계
(영속 캐시가 필요하면 Firestore로 확장). time.time() 사용 — 런타임 전용.
"""
import time
import threading
from collections import OrderedDict


class TTLCache:
    def __init__(self, maxsize=256, ttl=43200):  # 기본 12h
        self.maxsize = maxsize
        self.ttl = ttl
        self._store = OrderedDict()  # key -> (expires_at, value)
        self._lock = threading.RLock()  # ASGI 멀티스레드 접근 대비(codex)

    def get(self, key):
        with self._lock:
            item = self._store.get(key)
            if item is None:
                return None
            expires_at, value = item
            if time.time() >= expires_at:
                self._store.pop(key, None)
                return None
            self._store.move_to_end(key)  # LRU 갱신
            return value

    def set(self, key, value, ttl=None):
        ttl = self.ttl if ttl is None else ttl
        with self._lock:
            self._store[key] = (time.time() + ttl, value)
            self._store.move_to_end(key)
            while len(self._store) > self.maxsize:
                self._store.popitem(last=False)  # 가장 오래된 것 제거

    def clear(self):
        with self._lock:
            self._store.clear()
