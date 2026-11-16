"""source_item ↔ issue 다대다 관계(순수).

정본은 `links: [{issue_id, status, score, reason, at}]`. `issue_ids`는 status∈{auto,confirmed}인
조회용 파생 배열, `issue_id`/`link_status`는 첫 승인 관계(없으면 첫 관계)의 미러(구 코드 호환).
거절(rejected)된 관계는 자동 연결로 되살리지 않는다.
"""
import re

APPROVED = ("auto", "confirmed")

# 언론 별칭 → 정식 법률명. '조작기소 특검법'처럼 '{핵심어} 특검법' 또는 '{핵심어}법'으로 부르는 경우,
# 핵심어가 정식 법률명에 그대로 들어 있으면 같은 법안으로 본다(띄어쓰기·가운뎃점 무시).
# 핵심어는 한 단어 또는 띄어 쓴 두 단어('순직 해병 특검법')
_SPECIAL_PROSECUTOR = re.compile(r"([가-힣]{2,12}(?:\s[가-힣]{2,12})?)\s?(?:특검법안|특검법|특검)")
_LAW_SUFFIX = re.compile(r"([가-힣]{2,12}(?:\s[가-힣]{2,12})?)(?:법안|법)(?![가-힣])")
# 여러 법률명에 흔히 들어가 핵심어 구실을 못 하는 말
_GENERIC_CORE = {"위원회", "특별위원회", "특별", "일부개정", "전부개정", "개정", "기본", "지원", "진흥", "육성", "보호",
                 "관리", "운영", "촉진", "특례", "조치", "처벌", "관한", "위한", "대한민국", "국가", "국민", "정부",
                 "민생", "개혁", "방지", "강화", "완화",
                 # 특검·국정조사 법률명에 공통으로 들어가 사건을 가리지 못하는 말
                 "진상규명", "의혹", "특별검사", "수사", "국정조사", "임명", "사건", "조사"}


def _norm(text: str) -> str:
    return re.sub(r"[\s·ㆍ,.()\[\]'\"‘’“”]", "", text or "")


def _generic(core: str) -> bool:
    # 흔한 말 자체이거나 그 조각('별위원회'), 또는 흔한 말 앞에 한 글자만 붙은 것
    for g in _GENERIC_CORE:
        if core in g or (core.endswith(g) and len(core) - len(g) < 2):
            return True
    return False


def _word_starts(law_name: str) -> list:
    """법률명에서 단어가 시작하는 위치들을 기준으로 자른 꼬리 문자열(정규화). 핵심어는 단어 첫머리에서 시작해야 한다
    ('위치정보보호법'의 '정보보호'가 '개인정보 보호법'의 단어 중간에 걸리던 오연결 방지)."""
    parts = re.split(r"[\s·ㆍ,()\[\]]+", law_name or "")
    tails = []
    for i in range(len(parts)):
        tail = _norm("".join(parts[i:]))
        if tail:
            tails.append(tail)
    return tails


def _core_in_law(run: str, law_name: str, min_len: int) -> bool:
    """별칭 앞 한글 덩어리(run)의 뒷부분(앞말이 붙는 경우 대비) 중 min_len자 이상이
    정식 법률명의 어느 단어 첫머리에서 시작해 그대로 이어지는지."""
    run = _norm(run)
    tails = _word_starts(law_name)
    for i in range(0, len(run) - min_len + 1):
        core = run[i:]
        if not _generic(core) and any(t.startswith(core) for t in tails):
            return True
    return False


def law_mention(law_name: str, text: str):
    """text가 법안(law_name)을 가리키면 'exact'(정식명 그대로) 또는 'alias'(언론 별칭), 아니면 None."""
    law = law_name or ""
    text = text or ""
    if len(law) >= 4 and law in text:
        return "exact"
    law_n = _norm(law)
    if len(law_n) < 4:
        return None
    if "특별검사" in law_n:
        for m in _SPECIAL_PROSECUTOR.finditer(text):
            if _core_in_law(m.group(1), law, 3):
                return "alias"
    for m in _LAW_SUFFIX.finditer(text):
        if _core_in_law(m.group(1), law, 4):
            return "alias"
    return None


def _links(source: dict) -> list:
    return list(source.get("links") or [])


def _vote_title(source: dict) -> str:
    t = source.get("title") or ""
    return t[len("표결: "):] if t.startswith("표결: ") else ""


def has_link(source: dict, issue_id: str) -> bool:
    return any(l.get("issue_id") == issue_id for l in _links(source))


def is_rejected(source: dict, issue_id: str) -> bool:
    return any(l.get("issue_id") == issue_id and l.get("status") == "rejected" for l in _links(source))


def issue_ids_of(source: dict) -> list:
    out = []
    for l in _links(source):
        if l.get("status") in APPROVED and l.get("issue_id") not in out:
            out.append(l["issue_id"])
    return out


def _mirror(source: dict) -> dict:
    links = _links(source)
    first = next((l for l in links if l.get("status") in APPROVED), links[0] if links else None)
    source["issue_ids"] = issue_ids_of(source)
    source["issue_id"] = first["issue_id"] if first else None
    source["link_status"] = first["status"] if first else "new"
    return source


def add_link(source: dict, issue_id: str, status: str, score: float, reason: str, at: str) -> dict:
    src = dict(source)
    links = _links(src)
    if status != "rejected" and is_rejected(src, issue_id) and status in ("auto", "pending"):
        src["links"] = links
        return _mirror(src)
    links = [l for l in links if l.get("issue_id") != issue_id]
    links.append({"issue_id": issue_id, "status": status, "score": float(score or 0), "reason": reason, "at": at})
    src["links"] = links
    return _mirror(src)


def news_issue_link_score(source: dict, issue_blob: str, people) -> tuple:
    """뉴스 이슈용 점수. 정식 법률명 일치 12(auto), 언론 별칭 일치 10(auto), 제안자∩인물 5(pending)."""
    blob = issue_blob or ""
    law = source.get("law_name") or ""
    bill = source.get("bill") or {}
    name = bill.get("bill_name") or ""
    if source.get("procedural"):
        return (0, None)
    # 같은 법률을 고치는 개정안은 발의·표결 모두 여러 건이다(형사소송법 개정 = 보완수사권일 수도 전자소송일 수도).
    # 법률명만 같아서는 이 이슈가 다루는 안건이라는 근거가 약하므로 자동 연결하지 않고 검수 대기로.
    # 자동 연결은 고유 이름 법안(특검법·제정법 등)의 정식명/별칭 일치만(2026-11-16 Codex 리뷰).
    generic_amend = any(t in (source.get("title") or "") for t in ("일부개정법률안", "전부개정법률안"))
    if (len(law) >= 4 and law in blob) or (len(name) >= 4 and name in blob):
        return (5.0, "pending") if generic_amend else (12.0, "auto")
    if law_mention(law, blob) == "alias" or law_mention(name or _vote_title(source), blob) == "alias":
        return (5.0, "pending") if generic_amend else (10.0, "auto")
    proposers = set(bill.get("proposers") or [])
    if proposers and proposers & set(people or []):
        return (5.0, "pending")
    return (0, None)
