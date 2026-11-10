"""동적 OG 이미지 렌더러(순수 함수) 테스트."""
import io

from PIL import Image

from utils.og_image import (
    render_og_image, wrap_text, OG_W, OG_H, KIND_LABELS, _font,
)


def _png(b: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(b))
    img.load()
    return img


def test_renders_1200x630_png():
    b = render_og_image(title="추가경정예산안 처리", description="국회 심사 경과", kind="issue")
    img = _png(b)
    assert img.format == "PNG"
    assert img.size == (OG_W, OG_H) == (1200, 630)


def test_default_card_when_empty():
    b = render_og_image(title="", description=None, kind="issue")
    assert _png(b).size == (1200, 630)


def test_deterministic_bytes_for_same_input():
    a = render_og_image(title="같은 제목", description="같은 요약", kind="article")
    b = render_og_image(title="같은 제목", description="같은 요약", kind="article")
    assert a == b


def test_unknown_kind_falls_back_to_default_label():
    assert "issue" in KIND_LABELS and "article" in KIND_LABELS
    b = render_og_image(title="x", description="", kind="whatever")
    assert _png(b).size == (1200, 630)


def test_wrap_text_breaks_korean_by_word_then_char():
    font = _font("bold", 40)
    # 공백 어절 단위로 먼저 끊고, 한 어절이 너무 길면 글자 단위로 끊는다
    lines = wrap_text("국회 본회의 추가경정예산안 처리 경과와 쟁점 정리", font, max_width=400, max_lines=3)
    assert 1 < len(lines) <= 3
    for ln in lines:
        assert font.getlength(ln) <= 400 + 1
    long_word = "가" * 60
    lines2 = wrap_text(long_word, font, max_width=400, max_lines=2)
    assert len(lines2) == 2
    assert lines2[-1].endswith("…")


def test_wrap_text_truncates_with_ellipsis_at_max_lines():
    font = _font("bold", 40)
    text = " ".join(["쟁점"] * 80)
    lines = wrap_text(text, font, max_width=400, max_lines=3)
    assert len(lines) == 3
    assert lines[-1].endswith("…")
    assert font.getlength(lines[-1]) <= 400 + 1


def test_wrap_text_empty():
    font = _font("regular", 30)
    assert wrap_text("", font, max_width=400, max_lines=2) == []


def test_default_card_is_served_from_cache():
    from utils import og_image
    og_image._render_cached.cache_clear()
    render_og_image(title="", description="", kind="issue")
    render_og_image(title=None, description=None, kind="issue")
    assert og_image._render_cached.cache_info().hits >= 1
