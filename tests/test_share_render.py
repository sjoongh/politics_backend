from utils.share_render import render_share_html

BASE = dict(
    title="테스트 이슈",
    description="요약 설명",
    image_url="https://koreanpolitical.web.app/og-default.png",
    share_url="https://politicsbackend-ruby.vercel.app/share/issue/abc",
    redirect_url="https://koreanpolitical.web.app/?issue=abc",
)

def test_includes_og_title_and_url():
    h = render_share_html(**BASE)
    assert '<meta property="og:title" content="테스트 이슈">' in h
    assert '<meta property="og:url" content="https://politicsbackend-ruby.vercel.app/share/issue/abc">' in h
    assert '<meta name="twitter:card" content="summary_large_image">' in h

def test_escapes_html_in_title():
    h = render_share_html(**{**BASE, "title": '<script>alert(1)</script>'})
    assert "<script>alert(1)</script>" not in h
    assert "&lt;script&gt;" in h

def test_clips_long_title_and_description():
    h = render_share_html(**{**BASE, "title": "가" * 100, "description": "나" * 300})
    # og:title content 길이(… 포함) 61자 이하
    import re
    title = re.search(r'og:title" content="([^"]*)"', h).group(1)
    desc = re.search(r'og:description" content="([^"]*)"', h).group(1)
    assert len(title) <= 61 and title.endswith("…")
    assert len(desc) <= 151 and desc.endswith("…")

def test_defaults_when_empty():
    h = render_share_html(**{**BASE, "title": "", "description": ""})
    assert "브리핑 코리아 · 정치 브리핑" in h

def test_redirect_in_js_and_noscript():
    h = render_share_html(**BASE)
    assert "location.replace(" in h
    assert "https://koreanpolitical.web.app/?issue=abc" in h  # JS 문자열
    assert '<noscript><a href="https://koreanpolitical.web.app/?issue=abc"' in h

def test_script_break_is_neutralized():
    evil = "https://x/?a=</script><script>evil()</script>"
    h = render_share_html(**{**BASE, "redirect_url": evil})
    # 원본 </script> 시퀀스가 그대로 들어가면 안 됨
    assert "</script><script>evil()" not in h
