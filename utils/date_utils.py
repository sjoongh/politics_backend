"""
날짜 관련 유틸리티 함수
"""
from datetime import datetime, timezone
from typing import Optional

def get_current_utc_time() -> datetime:
    """현재 UTC 시간 반환"""
    return datetime.now(timezone.utc)

def parse_date_string(date_string: str) -> Optional[datetime]:
    """문자열을 datetime 객체로 변환"""
    try:
        # ISO 형식 시도
        return datetime.fromisoformat(date_string.replace('Z', '+00:00'))
    except ValueError:
        try:
            # 다른 형식들 시도
            formats = [
                '%Y-%m-%d %H:%M:%S',
                '%Y-%m-%d',
                '%Y/%m/%d %H:%M:%S',
                '%Y/%m/%d',
            ]

            for fmt in formats:
                try:
                    return datetime.strptime(date_string, fmt)
                except ValueError:
                    continue

            return None
        except:
            return None

def format_korean_date(date: datetime) -> str:
    """날짜를 한국어 형식으로 포맷"""
    return date.strftime('%Y년 %m월 %d일 %H시 %M분')

def get_relative_time(date: datetime) -> str:
    """상대적인 시간 표현 반환"""
    now = get_current_utc_time()

    # 시간대 정보가 없는 경우 UTC로 간주
    if date.tzinfo is None:
        date = date.replace(tzinfo=timezone.utc)

    diff = now - date

    if diff.days > 0:
        return f"{diff.days}일 전"
    elif diff.seconds > 3600:
        hours = diff.seconds // 3600
        return f"{hours}시간 전"
    elif diff.seconds > 60:
        minutes = diff.seconds // 60
        return f"{minutes}분 전"
    else:
        return "방금 전"