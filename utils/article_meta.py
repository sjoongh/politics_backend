"""이슈 문서의 기사 메타(article_meta) — 상세·digest가 기사를 다시 읽지 않도록
연결 시점에 매체·성향·시각만 남긴다. {article_id: {source, leaning, at}}"""
from datetime import datetime
from utils.source_bias import source_leaning


def _iso(v) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.isoformat()
    return str(v)


def meta_for(article: dict) -> dict:
    src = article.get("source") or ""
    at = _iso(article.get("created_at")) or _iso(article.get("published_at"))
    return {"source": src, "leaning": source_leaning(src), "at": at}


def merge_meta(existing: dict, articles) -> dict:
    out = dict(existing or {})
    for a in (articles or []):
        aid = a.get("id")
        if aid and aid not in out:
            out[aid] = meta_for(a)
    return out


def sorted_article_ids(meta: dict) -> list:
    return sorted((meta or {}).keys(), key=lambda i: (meta[i] or {}).get("at") or "", reverse=True)


def attach_articles(issue: dict, articles) -> dict:
    """이슈에 기사들을 연결했을 때 저장할 패치: 메타 병합 + 날짜 역순 article_ids.
    메타에 없는 기존 id(기사 문서를 모르는 경우)는 뒤에 보존한다."""
    meta = merge_meta(issue.get("article_meta") or {}, articles)
    ordered = sorted_article_ids(meta)
    known = set(ordered)
    tail = [i for i in (issue.get("article_ids") or []) if i not in known]
    return {"article_meta": meta, "article_ids": ordered + tail}
