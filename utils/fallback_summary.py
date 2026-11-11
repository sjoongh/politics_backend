"""AI 요약이 아직 없는 이슈의 규칙 기반 요약. 템플릿 안내문("여러 매체가 보도한 현안입니다") 대신
실제 정보(대표 기사 제목 / 법안·단계·날짜)를 쓴다. 빈 문자열을 돌려주지 않는다."""


def _short_date(s) -> str:
    s = str(s or "")
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        try:
            return f"{int(s[5:7])}.{int(s[8:10])}"
        except ValueError:
            return ""
    return ""


def fallback_summary(issue: dict, articles_by_id: dict) -> str:
    key = issue.get("auto_key") or ""
    if key.startswith("bill:"):
        parts = [issue.get("law_name") or issue.get("title") or "", issue.get("status") or "",
                 _short_date(issue.get("updated_at"))]
        return " · ".join(p for p in parts if p) or (issue.get("title") or "")
    meta = issue.get("article_meta") or {}
    ordered = sorted(meta.items(), key=lambda kv: (kv[1] or {}).get("at") or "", reverse=True)
    for want_center in (True, False):
        for aid, m in ordered:
            if want_center and (m or {}).get("leaning") != "center":
                continue
            title = ((articles_by_id or {}).get(aid) or {}).get("title")
            if title:
                return title
    return issue.get("title") or ""
