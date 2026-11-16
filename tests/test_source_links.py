from utils.source_links import add_link, has_link, is_rejected, news_issue_link_score, issue_ids_of


def test_add_link_updates_mirrors():
    s = add_link({"id": "s"}, "i1", "auto", 12.0, "law_name", "2026-11-10")
    assert s["issue_ids"] == ["i1"] and s["issue_id"] == "i1" and s["link_status"] == "auto"
    assert s["links"][0]["reason"] == "law_name" and has_link(s, "i1")


def test_rejected_not_in_issue_ids():
    s = add_link({"id": "s"}, "i1", "rejected", 0, "manual", "t")
    assert s["issue_ids"] == [] and is_rejected(s, "i1") and s["link_status"] == "rejected"


def test_replace_same_issue_and_keep_rejected():
    s = add_link({"id": "s"}, "i1", "pending", 5.0, "proposer", "t1")
    s = add_link(s, "i1", "confirmed", 5.0, "review", "t2")
    s = add_link(s, "i2", "rejected", 0, "review", "t3")
    s = add_link(s, "i2", "auto", 12.0, "law_name", "t4")   # 거절된 관계는 자동으로 되살리지 않는다
    assert issue_ids_of(s) == ["i1"] and len(s["links"]) == 2 and is_rejected(s, "i2")


def test_mirror_prefers_first_approved_link():
    s = add_link({"id": "s"}, "i1", "pending", 5.0, "x", "t")
    s = add_link(s, "i2", "auto", 12.0, "y", "t")
    assert s["issue_id"] == "i2" and s["link_status"] == "auto"


def test_score_exact_law_name():
    assert news_issue_link_score({"law_name": "국민연금법", "bill": {"bill_name": "국민연금법 일부개정법률안", "proposers": []}},
                                 "국민연금법 개정 논란", []) == (12.0, "auto")


def test_score_proposer_pending():
    assert news_issue_link_score({"law_name": "xx", "bill": {"bill_name": "yy", "proposers": ["김승원"]}}, "무관", ["김승원"]) == (5.0, "pending")


def test_score_short_law_name_ignored():
    assert news_issue_link_score({"law_name": "형법", "bill": None}, "형법 개정", []) == (0, None)


LAW_SP = "윤석열 정권 검찰청, 국가정보원, 감사원 등의 조작수사ㆍ조작기소 등 의혹의 진상규명을 위한 특별검사 임명 등에 관한 법률안"


def test_law_mention_alias_special_prosecutor():
    from utils.source_links import law_mention
    assert law_mention(LAW_SP, "‘조작기소 특검법’ 논란") == "alias"
    assert law_mention(LAW_SP, "민주당의조작기소 특검법 강행") == "alias"
    assert law_mention(LAW_SP, "‘선관위 특검법안’ 논란") is None          # 핵심어가 법률명에 없음
    assert law_mention("국민연금법", "국민연금법 개정 논의") == "exact"


def test_law_mention_alias_law_suffix_and_generic_core():
    from utils.source_links import law_mention
    assert law_mention("형사소송법 일부개정법률안", "개정 형사소송법 시행") == "alias"
    assert law_mention("지방주도성장을 위한 특별위원회 구성결의안", "특별위원회법 처리") is None   # 흔한 말
    assert law_mention("항만법", "불법 방법") is None


def test_news_link_score_alias_and_procedural():
    from utils.source_links import news_issue_link_score
    vote = {"type": "assembly_vote", "title": "표결: " + LAW_SP, "law_name": LAW_SP[:60], "procedural": False}
    assert news_issue_link_score(vote, "‘조작기소 특검법’ 논란 조작기소 특검법", []) == (10.0, "auto")
    proc = {"type": "assembly_vote", "title": "표결: 제437회국회 회기결정의 건", "law_name": "제437회국회 회기결정의 건",
            "procedural": True}
    assert news_issue_link_score(proc, "제437회국회 회기결정의 건", []) == (0, None)


def test_law_mention_rejects_mid_word_and_generic_cores():
    # Codex 리뷰 재현 사례: 단어 중간 조각·특검 법률 공통어만으로는 연결하지 않는다
    from utils.source_links import law_mention
    assert law_mention("개인정보 보호법", "위치정보보호법 처리 논란") is None
    sp = "순직 해병 수사 방해 및 사건 은폐 등의 진상규명을 위한 특별검사의 임명 등에 관한 법률안"
    assert law_mention(sp, "김건희 의혹 진상규명법 처리") is None
    assert law_mention(sp, "김건희 특검법 처리") is None
    assert law_mention(sp, "순직 해병 특검법 재표결") == "alias"


def test_generic_amendment_bill_is_pending_but_vote_is_auto():
    from utils.source_links import news_issue_link_score
    bill = {"type": "assembly_bill", "title": "형사소송법 일부개정법률안", "law_name": "형사소송법", "procedural": False}
    assert news_issue_link_score(bill, "보완수사권 폐지 형사소송법 논란", []) == (5.0, "pending")
    vote = {"type": "assembly_vote", "title": "표결: 형사소송법 일부개정법률안(대안)(법제사법위원장)", "law_name": "형사소송법",
            "procedural": False}
    assert news_issue_link_score(vote, "보완수사권 폐지 형사소송법 논란", []) == (12.0, "auto")
