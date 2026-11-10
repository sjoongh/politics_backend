"""파이프라인 단계 선택(순수). 가벼운 단계는 매시, 무거운 단계는 KST 3시간마다(0,3,…,21시)."""
LIGHT = ["collect_news"]
HEAVY = ["ingest_gov", "ingest_bills", "ingest_votes", "enrich_pending", "generate_bill_issues",
         "link_unlinked", "crosslink", "generate_news_issues", "link_news_issues",
         "summarize_pending_issues", "refresh_digest", "build_edition"]
DAILY = ["enrich_member_bills", "enrich_member_votes"]   # 의원 300명 전수 읽기 → 하루 1회(KST 03시)
HEAVY_EVERY_HOURS = 3
DAILY_HOUR = 3


def is_heavy_hour(kst_hour: int, every: int = HEAVY_EVERY_HOURS) -> bool:
    return kst_hour % every == 0


def select_steps(kst_hour: int, heavy=None, only=None, daily=None) -> list:
    if only:
        return [s for s in only if s in LIGHT + HEAVY + DAILY]
    run_heavy = is_heavy_hour(kst_hour) if heavy is None else bool(heavy)
    run_daily = (kst_hour == DAILY_HOUR) if daily is None else bool(daily)
    return LIGHT + (HEAVY if run_heavy else []) + (DAILY if run_daily else [])
