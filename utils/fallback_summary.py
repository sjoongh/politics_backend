"""AI 요약이 아직 없는 이슈의 규칙 기반 요약. 템플릿 안내문("여러 매체가 보도한 현안입니다") 대신
실제 정보(대표 기사 제목 / 표결 결과·날짜)를 쓴다. 빈 문자열을 돌려주지 않는다.

뉴스 이슈: 제목의 인용구를 담은 기사를 먼저 고른다(최신 기사만 고르면 오염된 연결 기사의 제목이 요약이 됐다).
법안 이슈: 제목(법률명)을 반복하지 않고 표결 결과·표결일·수치. 날짜는 문서 수정 시각이 아니라 기록 날짜."""


def _short_date(s) -> str:
    s = str(s or "")
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        try:
            return f"{int(s[5:7])}.{int(s[8:10])}"
        except ValueError:
            return ""
    if len(s) == 8 and s.isdigit():
        return f"{int(s[4:6])}.{int(s[6:8])}"
    return ""


def _bill_summary(issue: dict) -> str:
    vote = (issue.get("digest") or {}).get("vote") or issue.get("vote") or None
    if vote:
        date = _short_date(vote.get("date"))
        parts = [vote.get("result") or issue.get("status") or "", f"{date} 표결" if date else "",
                 f"찬성 {int(vote.get('yes') or 0)} · 반대 {int(vote.get('no') or 0)} · 기권 {int(vote.get('abstain') or 0)}"]
        return " · ".join(p for p in parts if p)
    date = _short_date(issue.get("record_date"))
    parts = [issue.get("law_name") or issue.get("title") or "", issue.get("status") or "", date]
    return " · ".join(p for p in parts if p) or (issue.get("title") or "")


def _phrases(issue: dict) -> list:
    people = set((issue.get("entities") or {}).get("people") or [])
    return [k for k in (issue.get("keywords") or []) if k and k not in people and len(k) >= 2]


def _phrase_hit(title: str, phrase: str, people) -> bool:
    """제목이 인용구를 담았는지: 통째로(띄어쓰기 무시) 또는 핵심 단어 절반 이상(최소 2개)."""
    from utils.crosslink_match import phrase_tokens
    t = (title or "").replace(" ", "")
    if phrase.replace(" ", "") in t:
        return True
    toks = [x for x in phrase_tokens(phrase) if x not in people]
    if len(toks) < 2:
        return False
    need = max(2, -(-len(toks) // 2))
    return sum(1 for x in toks if x in t) >= need


def fallback_summary(issue: dict, articles_by_id: dict) -> str:
    key = issue.get("auto_key") or ""
    if key.startswith("bill:"):
        return _bill_summary(issue)
    meta = issue.get("article_meta") or {}
    ordered = sorted(meta.items(), key=lambda kv: (kv[1] or {}).get("at") or "", reverse=True)
    phrases = _phrases(issue)
    people = set((issue.get("entities") or {}).get("people") or [])
    titled = [(aid, m, ((articles_by_id or {}).get(aid) or {}).get("title")) for aid, m in ordered]
    titled = [x for x in titled if x[2]]

    def pick(rows, want_center):
        for _aid, m, title in rows:
            if not want_center or (m or {}).get("leaning") == "center":
                return title
        return None

    if phrases:
        hits = [x for x in titled if any(_phrase_hit(x[2], p, people) for p in phrases)]
        title = pick(hits, True) or pick(hits, False)
        if title:
            return title
        # 인용구를 담은 기사가 없으면 근거 없는 요약을 만들지 않는다(제목과 같게 → 화면은 요약 줄을 숨김)
        return issue.get("title") or ""
    title = pick(titled, True) or pick(titled, False)
    return title or issue.get("title") or ""
