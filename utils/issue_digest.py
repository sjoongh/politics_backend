"""이슈 digest 순수 계산 (firebase 비의존, 테스트 대상).

목록·오늘 화면이 상세를 열지 않고도 '공식 기록 수 · 대표 표결 · 확인된 입장 · 보도 분포 · 순위'를
보이도록 이슈 문서에 미리 저장할 값을 만든다. 입력은 이미 메모리에 있는 이슈 문서와 연결 소스뿐이며
기사를 다시 읽지 않는다(article_meta 사용).

입장(stance) 원칙: 근거 유형(basis)을 반드시 단다.
- official: 정부 발표의 AI 보강 position(행위자는 부처명)
- vote: 표결의 정당별 찬반 관측치(다수결로 '입장'을 단정하지 않음)
- press: 보도에서 추출(기본 비활성, 상세에서만 표시)
법안 소스(actor '국회', position 'propose')는 입장이 아니므로 쓰지 않는다.
"""
from datetime import datetime, timezone
from utils.ministries import ministry_of

HALF_LIFE_HOURS = 72.0
AUTO_RANK_CAP = 40.0
MANUAL_BASE = 1000.0
LEANINGS = ("left", "center", "right", "foreign")


def count_sources(sources) -> dict:
    out = {"gov": 0, "bill": 0, "vote": 0}
    for s in (sources or []):
        t = s.get("type")
        if t == "gov_policy":
            out["gov"] += 1
        elif t == "assembly_bill":
            out["bill"] += 1
        elif t == "assembly_vote":
            out["vote"] += 1
    return out


def _vote_name(source) -> str:
    title = source.get("title") or ""
    return title[len("표결: "):] if title.startswith("표결: ") else (source.get("law_name") or title)


def representative_vote(sources):
    votes = [s for s in (sources or []) if s.get("type") == "assembly_vote" and s.get("vote")]
    if not votes:
        return None
    v = max(votes, key=lambda s: str(s.get("published_at") or ""))
    vo = v["vote"]
    return {"source_id": v.get("id"), "bill_name": _vote_name(v), "date": v.get("published_at") or "",
            "yes": int(vo.get("yes") or 0), "no": int(vo.get("no") or 0), "abstain": int(vo.get("abstain") or 0),
            "result": vo.get("result") or ""}


def stance_from_official(gov_sources) -> list:
    latest = {}
    for s in (gov_sources or []):
        if s.get("type") not in (None, "gov_policy") or not s.get("position"):
            continue
        actor = ministry_of((s.get("title") or "") + " " + (s.get("excerpt") or ""))
        at = str(s.get("published_at") or "")
        if actor in latest and str(latest[actor]["at"]) >= at:
            continue
        latest[actor] = {"actor": actor, "actor_type": "government", "position": s["position"],
                         "basis": "official", "evidence": s.get("claim_summary") or s.get("title") or "",
                         "url": s.get("url"), "source_id": s.get("id"), "at": at}
    return sorted(latest.values(), key=lambda r: r["at"], reverse=True)


def stance_from_vote(vote_source, max_parties: int = 4) -> list:
    if not vote_source or not vote_source.get("vote"):
        return []
    pb = vote_source["vote"].get("party_breakdown") or {}
    rows = []
    for party, c in pb.items():
        if not party:
            continue
        total = int(c.get("yes") or 0) + int(c.get("no") or 0) + int(c.get("abstain") or 0)
        if total == 0:
            continue
        rows.append({"actor": party, "actor_type": "party",
                     "position": {"yes": int(c.get("yes") or 0), "no": int(c.get("no") or 0),
                                  "abstain": int(c.get("abstain") or 0)},
                     "basis": "vote", "evidence": _vote_name(vote_source), "url": vote_source.get("url"),
                     "source_id": vote_source.get("id"), "at": str(vote_source.get("published_at") or ""),
                     "_total": total})
    rows.sort(key=lambda r: r["_total"], reverse=True)
    for r in rows:
        r.pop("_total", None)
    return rows[:max_parties]


def bias_from_meta(article_meta) -> dict:
    out = {"left": 0, "center": 0, "right": 0, "foreign": 0, "unknown": 0}
    for m in (article_meta or {}).values():
        lean = (m or {}).get("leaning")
        out[lean if lean in LEANINGS else "unknown"] += 1
    return out


def _parse_ts(s):
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00").replace(" ", "T"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def rank_score(issue: dict, counts: dict, last_activity_at, now: datetime) -> float:
    if not issue.get("auto_generated"):
        return MANUAL_BASE
    base = min(float(issue.get("newsworthiness") or 0.0), 20.0)
    base += 6.0 * (1 if counts.get("vote") else 0) + 3.0 * (1 if counts.get("bill") else 0) \
        + 2.0 * (1 if counts.get("gov") else 0)
    ts = _parse_ts(last_activity_at)
    if ts is not None:
        hours = max(0.0, (now - ts).total_seconds() / 3600.0)
        base *= 0.5 ** (hours / HALF_LIFE_HOURS)
    return round(min(base, AUTO_RANK_CAP), 3)


def build_digest(issue: dict, sources, now: datetime, press_stance=None) -> dict:
    sources = list(sources or [])
    meta = issue.get("article_meta") or {}
    counts = count_sources(sources)
    counts["media"] = len(meta)
    vote_src = None
    rep = representative_vote(sources)
    if rep:
        vote_src = next((s for s in sources if s.get("id") == rep["source_id"]), None)
    stance = stance_from_official([s for s in sources if s.get("type") == "gov_policy"]) \
        + stance_from_vote(vote_src) + list(press_stance or [])
    stance = stance[:6]
    times = [str(s.get("published_at") or "") for s in sources] + [str((m or {}).get("at") or "") for m in meta.values()]
    last = max((t for t in times if t), default=str(issue.get("updated_at") or ""))
    return {
        "counts": counts,
        "has_official": bool(counts["gov"] or counts["bill"] or counts["vote"]),
        "has_vote": bool(counts["vote"]),
        "has_gov": bool(counts["gov"]),
        "vote": rep,
        "stance": stance,
        "bias": bias_from_meta(meta),
        "last_activity_at": last,
        "rank": rank_score(issue, counts, last, now),
        "rank_at": now.isoformat(),
    }
