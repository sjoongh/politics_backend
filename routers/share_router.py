"""이슈/기사 공유용 OG 카드 라우트. 크롤러엔 OG HTML(200), 사람은 JS로 SPA 이동.

/share/{kind}/{id}/og.png 은 콘텐츠별 동적 OG 이미지(Pillow). 조회 실패(일시 장애)와
문서 없음을 구분해 캐시 정책을 다르게 가져간다(장애 결과가 CDN에 고착되지 않도록).
"""
import hashlib
import logging
import os
import re

from fastapi import APIRouter, Path, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from utils.og_image import OG_H, OG_W, render_og_image
from utils.rate_limit import RateLimiter
from utils.share_render import render_share_html

router = APIRouter()
log = logging.getLogger(__name__)

WEB_APP_URL = os.getenv("WEB_APP_URL", "https://koreanpolitical.web.app").rstrip("/")
SHARE_BASE_URL = os.getenv("SHARE_BASE_URL", "https://politicsbackend-ruby.vercel.app").rstrip("/")
OG_DEFAULT_IMAGE = os.getenv("OG_DEFAULT_IMAGE", f"{WEB_APP_URL}/og-default.png")

# 정상 응답: CDN 10분, 백그라운드 재검증 1일. 이미지는 바이트가 비싸므로 1일.
CACHE_CONTROL = "public, s-maxage=300, stale-while-revalidate=3600"
IMAGE_CACHE_CONTROL = "public, s-maxage=86400, stale-while-revalidate=604800"
# 일시 장애(Firestore 429 등): 캐시 금지 — 기본 카드가 하루 동안 고착되면 안 됨
ERROR_CACHE_CONTROL = "no-store"

# Firestore 문서 ID 형태만 허용(무작위 ID로 DB 조회/렌더 비용 유발 방지)
ID_PATTERN = r"^[A-Za-z0-9_-]{1,80}$"
_ID_RE = re.compile(ID_PATTERN)

# 형식에 맞는 임의 ID 난타(매번 Firestore 조회+렌더) 1차 방어. 크롤러 정상 사용량엔 넉넉.
_og_limiter = RateLimiter(max_calls=60, window_sec=60)


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    return (xff.split(",")[0].strip() if xff else None) or (request.client.host if request.client else "?")


def _rate_limited(request: Request):
    """한도 초과 시 기본 이미지로 302(렌더/조회 비용 0). 아니면 None."""
    if _og_limiter.allow(_client_ip(request)):
        return None
    return RedirectResponse(OG_DEFAULT_IMAGE, status_code=302,
                            headers={"Cache-Control": ERROR_CACHE_CONTROL, "Retry-After": "60"})


class FetchFailed:
    """조회 자체가 실패했음을 나타내는 sentinel(문서 없음 None 과 구분)."""


FETCH_FAILED = FetchFailed()


def _version(d: dict) -> str:
    """제목/요약 갱신 시 og.png URL(?v=)이 바뀌어 CDN·플랫폼 캐시를 깨도록 하는 짧은 해시."""
    raw = f"{d.get('updated_at') or ''}|{d.get('title') or ''}|{d.get('summary') or d.get('description') or ''}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]


def _fetch_issue_meta(issue_id: str):
    """Firestore에서 이슈 제목/요약만 읽음(뷰카운트 등 부작용 없음)."""
    try:
        from firebase.firebase_config import db
        from services.issue_service import issue_service
        issue_id = issue_service.resolve_issue_id(issue_id)
        doc = db.collection("issues").document(issue_id).get()
        if not doc.exists:
            return None
        d = doc.to_dict()
        return {"title": d.get("title"), "description": d.get("summary") or d.get("description"),
                "version": _version(d)}
    except Exception as e:  # noqa: BLE001
        log.warning("share issue fetch failed: %s", e)
        return FETCH_FAILED


def _fetch_article_meta(article_id: str):
    try:
        from firebase.firebase_config import db
        doc = db.collection("articles").document(article_id).get()
        if not doc.exists:
            return None
        d = doc.to_dict()
        return {"title": d.get("title"), "description": d.get("summary"), "version": _version(d)}
    except Exception as e:  # noqa: BLE001
        log.warning("share article fetch failed: %s", e)
        return FETCH_FAILED


def _og_image_url(kind: str, content_id: str, meta) -> str:
    url = f"{SHARE_BASE_URL}/share/{kind}/{content_id}/og.png"
    if isinstance(meta, dict) and meta.get("version"):
        url += f"?v={meta['version']}"
    return url


def _html(kind: str, content_id: str, meta, share_url: str, redirect_url: str) -> HTMLResponse:
    failed = meta is FETCH_FAILED
    m = meta if isinstance(meta, dict) else {}
    body = render_share_html(
        title=m.get("title") or "",
        description=m.get("description") or "",
        image_url=_og_image_url(kind, content_id, m) if isinstance(meta, dict) else OG_DEFAULT_IMAGE,
        image_width=OG_W,
        image_height=OG_H,
        share_url=share_url,
        # 문서 없음은 홈으로, 일시 조회 장애는 원래 링크를 보존해 재시도 가능하게.
        redirect_url=WEB_APP_URL if meta is None else redirect_url,
    )
    return HTMLResponse(content=body, status_code=200,
                        headers={"Cache-Control": ERROR_CACHE_CONTROL if failed else CACHE_CONTROL})


def _png(kind: str, meta) -> Response:
    """동적 OG PNG. 렌더 실패 시 정적 기본 이미지로 302(크롤러가 이미지를 못 받는 상황 방지)."""
    failed = meta is FETCH_FAILED
    m = meta if isinstance(meta, dict) else {}
    try:
        data = render_og_image(title=m.get("title"), description=m.get("description"), kind=kind)
    except Exception as e:  # noqa: BLE001
        log.error("og image render failed: %s", e)
        return RedirectResponse(OG_DEFAULT_IMAGE, status_code=302,
                                headers={"Cache-Control": ERROR_CACHE_CONTROL})
    return Response(content=data, media_type="image/png",
                    headers={"Cache-Control": ERROR_CACHE_CONTROL if failed else IMAGE_CACHE_CONTROL})


@router.get("/share/issue/{issue_id}")
def share_issue(issue_id: str = Path(..., pattern=ID_PATTERN)):
    return _html(
        "issue", issue_id, _fetch_issue_meta(issue_id),
        share_url=f"{SHARE_BASE_URL}/share/issue/{issue_id}",
        redirect_url=f"{WEB_APP_URL}/?issue={issue_id}",
    )


@router.get("/share/article/{article_id}")
def share_article(article_id: str = Path(..., pattern=ID_PATTERN)):
    return _html(
        "article", article_id, _fetch_article_meta(article_id),
        share_url=f"{SHARE_BASE_URL}/share/article/{article_id}",
        redirect_url=f"{WEB_APP_URL}/?article={article_id}",
    )


@router.get("/share/issue/{issue_id}/og.png")
def share_issue_og(request: Request, issue_id: str = Path(..., pattern=ID_PATTERN)):
    return _rate_limited(request) or _png("issue", _fetch_issue_meta(issue_id))


@router.get("/share/article/{article_id}/og.png")
def share_article_og(request: Request, article_id: str = Path(..., pattern=ID_PATTERN)):
    return _rate_limited(request) or _png("article", _fetch_article_meta(article_id))
