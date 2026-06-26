"""아주 가벼운 IP 단위 레이트리밋 (순수 로직, 테스트 대상).

서버리스라 인스턴스별 인메모리 — 전역 정확도는 낮지만, 한 IP가 warm 인스턴스에서
짧은 시간에 비싼 AI 엔드포인트를 난타하는 것을 막는 1차 방어. (전역 강제는 Vercel WAF/
영속 저장 필요 — 별도 운영 항목.) time.time() 사용.
"""
import time
from collections import deque


class RateLimiter:
    def __init__(self, max_calls=10, window_sec=60, maxsize=2000):
        self.max_calls = max_calls
        self.window = window_sec
        self.maxsize = maxsize
        self._hits = {}  # key -> deque[timestamps]

    def allow(self, key, now=None):
        """key(IP 등)가 윈도우 내 허용 한도 이내면 True, 초과면 False."""
        now = now if now is not None else time.time()
        dq = self._hits.get(key)
        if dq is None:
            if len(self._hits) >= self.maxsize:      # 메모리 상한(가장 오래된 키 정리)
                self._hits.pop(next(iter(self._hits)), None)
            dq = self._hits[key] = deque()
        cutoff = now - self.window
        while dq and dq[0] < cutoff:                 # 윈도우 밖 제거
            dq.popleft()
        if len(dq) >= self.max_calls:
            return False
        dq.append(now)
        return True

    def retry_after(self, key, now=None):
        now = now if now is not None else time.time()
        dq = self._hits.get(key)
        if not dq:
            return 0
        return max(0, int(self.window - (now - dq[0])))
