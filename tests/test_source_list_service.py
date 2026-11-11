import services.source_list_service as mod
from tests.test_issue_service_list_v2 import ListDB
from utils.cursor import decode_cursor


def _db():
    data = {}
    for n in range(1, 6):
        data[f"s{n}"] = {"id": f"s{n}", "type": "assembly_vote", "title": f"표결 {n}", "published_at": f"2026-11-0{n}",
                         "law_name": "L", "procedural": False, "url": "u", "issue_ids": [], "link_status": "new",
                         "vote": {"yes": n, "no": 0, "abstain": 0, "result": "가결", "party_breakdown": {}}}
    data["g"] = {"id": "g", "type": "gov_policy", "title": "정부", "published_at": "2026-11-09T00:00:00Z"}
    return ListDB({"source_items": data})


def test_list_desc_and_cursor(monkeypatch):
    monkeypatch.setattr(mod, "db", _db())
    out = mod.source_list_service.list("assembly_vote", None, 2)["data"]
    assert [i["id"] for i in out["items"]] == ["s5", "s4"] and out["next_cursor"]
    assert decode_cursor(out["next_cursor"]) == {"p": "2026-11-04", "i": "s4"}
    nxt = mod.source_list_service.list("assembly_vote", out["next_cursor"], 2)["data"]
    assert [i["id"] for i in nxt["items"]] == ["s3", "s2"]
    assert "party_breakdown" not in nxt["items"][0]["vote"]   # 표시 필드만


def test_list_filters_type(monkeypatch):
    monkeypatch.setattr(mod, "db", _db())
    out = mod.source_list_service.list("gov_policy", None, 30)["data"]
    assert [i["id"] for i in out["items"]] == ["g"] and out["next_cursor"] is None
