"""수집 관련 설정 순수 함수 (firebase 비의존, 테스트 대상)."""
import os

DEFAULT_AI_THROTTLE = 2.0


def ai_throttle_seconds() -> float:
    """기사당 AI 호출 간 대기(초). env AI_THROTTLE_SEC, 기본 2.0, 음수는 0으로."""
    raw = os.getenv("AI_THROTTLE_SEC")
    if raw is None:
        return DEFAULT_AI_THROTTLE
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_AI_THROTTLE
    return max(0.0, val)
