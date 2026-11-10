"""공유용 동적 OG 이미지(1200×630 PNG)를 Pillow로 그리는 순수 함수.

FastAPI/Firestore 비의존. 서버리스 콜드스타트를 고려해 폰트·배경은 프로세스 내 캐시.
크로미움/Playwright 없이 동작하도록 Noto Sans KR OTF를 assets/fonts 에 번들한다.
"""
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OG_W, OG_H = 1200, 630
PAD = 80

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
FONT_FILES = {
    "bold": FONT_DIR / "NotoSansKR-Bold.otf",
    "regular": FONT_DIR / "NotoSansKR-Regular.otf",
}

KIND_LABELS = {"issue": "이슈 브리핑", "article": "뉴스 브리핑"}
DEFAULT_LABEL = "실시간 정치 브리핑"
DEFAULT_TITLE = "브리핑 코리아"
DEFAULT_DESC = "뉴스 · 정부 · 국회를 한눈에 — 1차 소스 맥락 엔진"
BRAND = "브리핑 코리아"
DOMAIN = "koreanpolitical.web.app"

# 입력 길이 상한(렌더 비용 bound). 줄바꿈 단계에서 어차피 3줄/2줄로 잘린다.
TITLE_MAX_CHARS = 120
DESC_MAX_CHARS = 200

# 팔레트(기존 og-default.png 톤)
C_BG_A = (14, 110, 118)      # teal (좌상)
C_BG_B = (12, 54, 66)        # deep teal (우하)
C_MINT = (127, 245, 220)
C_WHITE = (255, 255, 255)
C_MUTED = (196, 222, 222)
C_PILL = (22, 92, 100)
C_GRID = (255, 255, 255, 10)


@lru_cache(maxsize=8)
def _font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    path = FONT_FILES[weight]
    return ImageFont.truetype(str(path), size)


@lru_cache(maxsize=1)
def _background() -> Image.Image:
    """대각 그라데이션 + 은은한 그리드 + 좌측 민트 액센트 바. 1회 생성 후 복사해 씀."""
    grad = Image.new("RGB", (OG_W, OG_H))
    px = grad.load()
    denom = float(OG_W + OG_H)
    for y in range(OG_H):
        for x in range(OG_W):
            t = (x + y) / denom
            px[x, y] = tuple(int(a + (b - a) * t) for a, b in zip(C_BG_A, C_BG_B))
    img = grad.convert("RGBA")
    overlay = Image.new("RGBA", (OG_W, OG_H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for x in range(0, OG_W, 60):
        od.line([(x, 0), (x, OG_H)], fill=C_GRID, width=1)
    for y in range(0, OG_H, 60):
        od.line([(0, y), (OG_W, y)], fill=C_GRID, width=1)
    img = Image.alpha_composite(img, overlay)
    d = ImageDraw.Draw(img)
    d.rectangle([(0, 0), (14, OG_H)], fill=C_MINT)
    return img.convert("RGB")


def _clip(s, n: int) -> str:
    s = (s or "").strip()
    s = " ".join(s.split())  # 개행/연속 공백 정리
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _fit_with_ellipsis(line: str, font, max_width: float) -> str:
    """line 끝에 '…'를 붙여도 max_width 안에 들어오도록 뒤에서부터 잘라냄."""
    ell = "…"
    while line and font.getlength(line + ell) > max_width:
        line = line[:-1].rstrip()
    return line + ell


def _break_long_word(word: str, font, max_width: float) -> list:
    """공백 없는 긴 어절을 글자 단위로 쪼갬."""
    chunks, cur = [], ""
    for ch in word:
        if font.getlength(cur + ch) <= max_width:
            cur += ch
        else:
            if cur:
                chunks.append(cur)
            cur = ch
    if cur:
        chunks.append(cur)
    return chunks


def wrap_text(text: str, font, max_width: float, max_lines: int) -> list:
    """어절(공백) 우선 줄바꿈, 어절이 너무 길면 글자 단위. max_lines 초과분은 '…'로 생략."""
    text = " ".join((text or "").split())
    if not text or max_lines <= 0:
        return []
    lines, cur = [], ""
    for word in text.split(" "):
        pieces = [word] if font.getlength(word) <= max_width else _break_long_word(word, font, max_width)
        for piece in pieces:
            cand = piece if not cur else cur + " " + piece
            if font.getlength(cand) <= max_width:
                cur = cand
            else:
                if cur:
                    lines.append(cur)
                cur = piece
                if len(lines) >= max_lines:
                    break
        if len(lines) >= max_lines:
            break
    if cur and len(lines) < max_lines:
        lines.append(cur)
        cur = ""
    truncated = bool(cur) or (len(lines) == max_lines and _remaining(text, lines))
    if truncated and lines:
        lines[-1] = _fit_with_ellipsis(lines[-1], font, max_width)
    return lines[:max_lines]


def _remaining(text: str, lines: list) -> bool:
    """줄바꿈 결과에 담기지 못한 글자가 남았는지(공백 제외 길이 비교)."""
    used = sum(len(l.replace(" ", "")) for l in lines)
    return used < len(text.replace(" ", ""))


def render_og_image(*, title, description, kind) -> bytes:
    """1200×630 PNG 바이트. 같은 입력 → 같은 바이트(캐시 친화)."""
    label = KIND_LABELS.get(kind or "", DEFAULT_LABEL)
    title = _clip(title, TITLE_MAX_CHARS) or DEFAULT_TITLE
    desc = _clip(description, DESC_MAX_CHARS) or DEFAULT_DESC

    img = _background().copy()
    d = ImageDraw.Draw(img)
    content_w = OG_W - PAD * 2

    # 라벨 pill
    f_label = _font("bold", 26)
    lw = f_label.getlength(label)
    pill = (PAD, 64, PAD + int(lw) + 56, 64 + 50)
    d.rounded_rectangle(pill, radius=25, fill=C_PILL)
    d.ellipse([(PAD + 20, 64 + 19), (PAD + 32, 64 + 31)], fill=C_MINT)
    d.text((PAD + 42, 64 + 9), label, font=f_label, fill=C_MINT)

    # 제목(최대 3줄) — 길이에 따라 폰트 크기 단계 조정
    title_size = 64 if len(title) <= 40 else 56
    f_title = _font("bold", title_size)
    t_lines = wrap_text(title, f_title, content_w, max_lines=3)
    y = 160
    line_h = int(title_size * 1.28)
    for ln in t_lines:
        d.text((PAD, y), ln, font=f_title, fill=C_WHITE)
        y += line_h

    # 요약(최대 2줄)
    f_desc = _font("regular", 30)
    y += 18
    for ln in wrap_text(desc, f_desc, content_w, max_lines=2):
        if y > OG_H - 130:
            break
        d.text((PAD, y), ln, font=f_desc, fill=C_MUTED)
        y += 44

    # 푸터
    f_brand = _font("bold", 28)
    f_dom = _font("regular", 24)
    fy = OG_H - 86
    d.text((PAD, fy), BRAND, font=f_brand, fill=C_WHITE)
    bx = PAD + f_brand.getlength(BRAND) + 18
    d.line([(bx, fy + 6), (bx, fy + 32)], fill=C_MUTED, width=2)
    d.text((bx + 18, fy + 5), DOMAIN, font=f_dom, fill=C_MUTED)

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=False, compress_level=6)
    return buf.getvalue()
