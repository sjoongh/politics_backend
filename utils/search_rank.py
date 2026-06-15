"""자연어 검색 랭킹 (순수 로직, firebase/AI 비의존 — 테스트 대상).

Gemini가 구조화한 parsed(keywords/category/entities/parties/date_preset)를
기사 후보에 적용해 점수화한다. AI가 없을 때는 parsed=None으로 두고
query 부분문자열 폴백 점수만 사용한다.
"""
import re
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))

# date_preset -> 기준 시각으로부터의 윈도우(일). today는 별도 처리.
_PRESET_DAYS = {"recent": 7, "week": 7, "month": 30, "year": 365}


def _parse_ts(article):
    v = article.get("published_at") or article.get("created_at")
    if not v:
        return None
    s = str(v).replace(" ", "T").replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _within_preset(dt, preset, now):
    if dt is None or not preset:
        return None  # 알 수 없음
    if preset == "today":
        start = now.astimezone(KST).replace(hour=0, minute=0, second=0, microsecond=0)
        return dt >= start
    days = _PRESET_DAYS.get(preset)
    if days is None:
        return None
    return dt >= (now - timedelta(days=days))


def _kw_list(article):
    """keywords를 안전하게 문자열 리스트로(비리스트/비문자 방어)."""
    kws = article.get("keywords")
    if not isinstance(kws, list):
        return []
    return [str(k) for k in kws if k is not None]


def _text_blob(article):
    return (
        (article.get("title") or "") + " " +
        (article.get("ai_summary") or "") + " " +
        " ".join(_kw_list(article))
    ).lower()


def score_article(article, parsed, query, now):
    """단일 기사 점수 + 매칭 사유. 반환: (score: float, reasons: list[str]).

    핵심 규칙: '내용 관련성'(키워드/엔티티/카테고리/제목/본문)이 0이면 제외한다.
    최신성·기간은 내용이 매칭된 기사에만 적용하는 '수식어'다(무관한 최신 기사 유입 방지)."""
    reasons = []
    content = 0.0  # 내용 관련성 점수
    cat_only = 0.0  # 카테고리만 맞는 약한 신호(단독으로는 통과시키지 않음)
    blob = _text_blob(article)
    title_l = (article.get("title") or "").lower()
    kw_set = {k.lower() for k in _kw_list(article)}

    if parsed:
        q_kw = [str(k).lower() for k in (parsed.get("keywords") or []) if k]
        kw_hits = sum(1 for k in q_kw if k in kw_set or k in blob)
        if kw_hits:
            content += kw_hits * 3
            reasons.append("keywords")
        ents = [str(e).lower() for e in (parsed.get("entities") or []) + (parsed.get("parties") or []) if e]
        ent_hits = sum(1 for e in ents if e in blob)
        if ent_hits:
            content += ent_hits * 3
            reasons.append("entity")
        if any(k in title_l for k in q_kw):
            content += 1.5
            reasons.append("title")
        # 카테고리 일치는 약한 보조(저장값 체계가 섞여 있어 부분일치 허용 — codex)
        cat, acat = parsed.get("category"), article.get("category")
        if cat and acat and (cat in acat or acat in cat):
            cat_only = 2.0

    # 원 질의 매칭(폴백 및 보강)
    q = (query or "").strip().lower()
    if q and (q in title_l):
        content += 2.5
        if "title" not in reasons:
            reasons.append("title")
    elif q and (q in blob):
        content += 1.0
        if "text" not in reasons:
            reasons.append("text")
    elif q:
        # 긴 자연어 질의: 토큰 단위로 부분 매칭(폴백 0건 방지 — codex)
        terms = [t for t in re.split(r"[\s,·]+", q) if len(t) >= 2]
        term_hits = sum(1 for t in terms if t in blob)
        if term_hits:
            content += term_hits * 0.8
            if "text" not in reasons:
                reasons.append("text")

    # 내용 관련성이 전혀 없으면 탈락(최신/카테고리 단독으로는 통과 불가)
    if content <= 0:
        return 0.0, []

    score = content + cat_only
    if cat_only:
        reasons.append("category")

    # 기간: 내용 매칭된 기사에만 적용
    if parsed:
        within = _within_preset(_parse_ts(article), parsed.get("date_preset"), now)
        if within is True:
            score += 2
            reasons.append("recent")
        elif within is False:
            score -= 1.5  # 요청 기간 밖이면 감점

    # 최신성 미세 가중(동점 정렬 보조)
    dt = _parse_ts(article)
    if dt is not None:
        age_days = max(0.0, (now - dt).total_seconds() / 86400.0)
        score += max(0.0, 1.0 - age_days / 30.0) * 0.5

    return score, reasons


def rank_articles(articles, parsed, query, limit=20, now=None):
    """후보 기사들을 점수순으로 정렬해 상위 limit개 반환(점수>0만)."""
    now = now or datetime.now(timezone.utc)
    scored = []
    for a in articles:
        s, reasons = score_article(a, parsed, query, now)
        if s > 0:
            item = dict(a)
            item["score"] = round(s, 2)
            item["matched_reasons"] = reasons
            scored.append(item)
    scored.sort(key=lambda x: (x["score"], str(x.get("published_at") or "")), reverse=True)
    return scored[:limit]
