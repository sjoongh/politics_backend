from pathlib import Path

from utils.korea_briefing import parse_press_list, PRESS_LIST_URL
from utils.source_item import normalize_gov_policy

FIXTURE = (Path(__file__).parent / "fixtures" / "korea_press_list.html").read_text(encoding="utf-8")


def test_parses_title_link_date_ministry():
    items = parse_press_list(FIXTURE)
    assert len(items) == 2
    first = items[0]
    assert first["title"] == "송미령 장관, 김장 한 포기 더 담고 이웃과 따뜻한 정 나누기 당부"
    assert first["link"] == "https://www.korea.kr/briefing/pressReleaseView.do?newsId=156788894"
    assert first["date"] == "2026-11-12"
    assert first["ministry"] == "농림축산식품부"
    assert "&nbsp;" not in first["description"] and first["description"].startswith("농림축산식품부")


def test_link_has_no_tracking_params():
    for it in parse_press_list(FIXTURE):
        assert "pageIndex" not in it["link"] and "startDate" not in it["link"]


def test_garbage_html_returns_empty():
    assert parse_press_list("<html>Error</html>") == []
    assert parse_press_list("") == []


def test_normalized_source_keeps_ministry_and_id_is_stable():
    it = parse_press_list(FIXTURE)[0]
    s = normalize_gov_policy(it)
    assert s["ministry"] == "농림축산식품부"
    assert s["published_at"] == "2026-11-12"
    assert s["type"] == "gov_policy" and s["actor_type"] == "government"
    assert normalize_gov_policy({**it, "link": it["link"] + "&pageIndex=3"})["id"] == s["id"]


def test_list_url_is_press_release_list():
    assert PRESS_LIST_URL.startswith("https://www.korea.kr/briefing/pressReleaseList.do")
