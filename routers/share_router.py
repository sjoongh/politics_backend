"""이슈/기사 공유용 OG 카드 라우트. 크롤러엔 OG HTML(200), 사람은 JS로 SPA 이동."""
import os
import logging

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from utils.share_render import render_share_html

router = APIRouter()
log = logging.getLogger(__name__)

WEB_APP_URL = os.getenv("WEB_APP_URL", "https://koreanpolitical.web.app").rstrip("/")
SHARE_BASE_URL = os.getenv("SHARE_BASE_URL", "https://politicsbackend-ruby.vercel.app").rstrip("/")
OG_DEFAULT_IMAGE = os.getenv("OG_DEFAULT_IMAGE", f"{WEB_APP_URL}/og-default.png")
CACHE_CONTROL = "public, s-maxage=600, stale-while-revalidate=86400"


def _fetch_issue_meta(issue_id: str):
    """Firestore에서 이슈 제목/요약만 읽음(뷰카운트 등 부작용 없음)."""
    try:
        from firebase.firebase_config import db
        doc = db.collection("issues").document(issue_id).get()
        if not doc.exists:
            return None
        d = doc.to_dict()
        return {"title": d.get("title"), "description": d.get("summary") or d.get("description")}
    except Exception as e:  # noqa: BLE001
        log.warning("share issue fetch failed: %s", e)
        return None


def _fetch_article_meta(article_id: str):
    try:
        from firebase.firebase_config import db
        doc = db.collection("articles").document(article_id).get()
        if not doc.exists:
            return None
        d = doc.to_dict()
        return {"title": d.get("title"), "description": d.get("summary")}
    except Exception as e:  # noqa: BLE001
        log.warning("share article fetch failed: %s", e)
        return None


def _html(meta, share_url, redirect_url) -> HTMLResponse:
    meta = meta or {}
    body = render_share_html(
        title=meta.get("title") or "",
        description=meta.get("description") or "",
        image_url=OG_DEFAULT_IMAGE,
        share_url=share_url,
        redirect_url=redirect_url,
    )
    return HTMLResponse(content=body, status_code=200,
                        headers={"Cache-Control": CACHE_CONTROL})


@router.get("/share/issue/{issue_id}")
async def share_issue(issue_id: str):
    return _html(
        _fetch_issue_meta(issue_id),
        share_url=f"{SHARE_BASE_URL}/share/issue/{issue_id}",
        redirect_url=f"{WEB_APP_URL}/?issue={issue_id}",
    )


@router.get("/share/article/{article_id}")
async def share_article(article_id: str):
    return _html(
        _fetch_article_meta(article_id),
        share_url=f"{SHARE_BASE_URL}/share/article/{article_id}",
        redirect_url=f"{WEB_APP_URL}/?article={article_id}",
    )
