"""날짜별 판(edition) 순수 계산. 날짜 경계는 KST, 소스의 published_at 기준(기사 수집 시각은 쓰지 않는다)."""
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
TOP_N = 3
OTHER_MAX = 30
SNAPSHOT_KEYS = ("id", "title", "summary", "status", "category")


def kst_date(ts):
    if not ts:
        return None
    s = str(ts).strip()
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        return s
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00").replace(" ", "T"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(KST).strftime("%Y-%m-%d")


def _snapshot(issue: dict) -> dict:
    dg = issue.get("digest") or {}
    out = {k: issue.get(k) for k in SNAPSHOT_KEYS}
    out["counts"] = dg.get("counts") or {}
    out["vote"] = dg.get("vote")
    out["stance"] = [s for s in (dg.get("stance") or []) if s.get("basis") in ("official", "vote")][:3]
    return out


def _active_on(issues, date):
    return [i for i in (issues or []) if i.get("active") is not False
            and kst_date((i.get("digest") or {}).get("last_activity_at")) == date]


def select_top_issues(issues, date, n=TOP_N) -> list:
    day = _active_on(issues, date)
    day.sort(key=lambda i: float((i.get("digest") or {}).get("rank") or 0), reverse=True)
    return [_snapshot(i) for i in day[:n]]


def _source_row(s: dict) -> dict:
    row = {k: s.get(k) for k in ("id", "type", "title", "law_name", "published_at", "procedural", "url")}
    row["issue_ids"] = list(s.get("issue_ids") or ([s["issue_id"]] if s.get("issue_id") and s.get("link_status") in ("auto", "confirmed") else []))
    if s.get("vote"):
        v = s["vote"]
        row["vote"] = {k: v.get(k) for k in ("yes", "no", "abstain", "result")}
    return row


def build_edition(date: str, issues, sources, overview) -> dict:
    top = select_top_issues(issues, date)
    top_ids = {t["id"] for t in top}
    day_sources = [s for s in (sources or []) if kst_date(s.get("published_at")) == date]
    votes = [_source_row(s) for s in day_sources if s.get("type") == "assembly_vote"]
    bills = [_source_row(s) for s in day_sources if s.get("type") == "assembly_bill"]
    gov = [_source_row(s) for s in day_sources if s.get("type") == "gov_policy"]
    others = _active_on(issues, date)
    others.sort(key=lambda i: float((i.get("digest") or {}).get("rank") or 0), reverse=True)
    other_ids = [i["id"] for i in others if i["id"] not in top_ids][:OTHER_MAX]
    return {
        "date": date,
        "top_issues": top,
        "assembly": {"votes": votes, "bills": bills},
        "government": gov,
        "other_issue_ids": other_ids,
        "overview": overview or None,
        "built_at": datetime.now(timezone.utc).isoformat(),
    }
