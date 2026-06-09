"""의원 책임성 법적 가드레일 순수 로직 (firebase 비의존, 테스트 대상)."""

MEMBER_DISCLAIMER = (
    "본 정보는 중앙선거관리위원회 공직선거 후보자 공개자료 등 공식 출처를 기반으로 하며, "
    "확정 판결만 표기합니다. 오류가 있을 경우 정정 요청을 받습니다."
)


def confirmed_records(records):
    """확정(is_final=True) 전과만 반환."""
    return [r for r in (records or []) if r.get("is_final", False)]


def criminal_count(records):
    """확정 전과 건수."""
    return len(confirmed_records(records))


def has_missing_source(records):
    """전과 중 source_url이 비었거나 없는 게 하나라도 있으면 True."""
    return any(not (r.get("source_url") or "").strip() for r in (records or []))
