"""1차 소스 정규화 순수 로직 (firebase/AI 비의존, 테스트 대상)."""
import re
import hashlib
from urllib.parse import urlsplit, parse_qs
from utils.law_name import normalize_law_name, is_procedural

_TAG = re.compile(r"<[^>]+>")
_PARTIES = ["더불어민주당", "민주당", "국민의힘", "조국혁신당", "개혁신당", "진보당",
            "정의당", "기본소득당", "사회민주당"]


def strip_html(text):
    return _TAG.sub("", text or "").strip()


def make_source_id(actor_type, url):
    """actor_type + url의 안정 키(중복제거). 추적 파라미터 제거 후 식별자만 사용."""
    parts = urlsplit(url or "")
    qs = parse_qs(parts.query)
    ident = qs.get("newsId", [""])[0] or qs.get("billId", [""])[0] or parts.path
    raw = f"{actor_type}:{parts.netloc}{parts.path}:{ident}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def extract_entities(text):
    t = text or ""
    matched = [p for p in _PARTIES if p in t]
    # 부분문자열 중복 제거: '더불어민주당' 매칭 시 '민주당' 제외(오탐 방지 — codex)
    parties = [p for p in matched if not any(p != o and p in o for o in matched)]
    bills = re.findall(r"(?:의안번호|의안)\s*제?\s*(\d{6,})", t) + re.findall(r"\b(\d{7})\b", t)
    return {"people": [], "parties": sorted(set(parties)), "bills": sorted(set(bills))}


def normalize_gov_policy(item):
    """korea.kr 정책브리핑 RSS item dict → source_item."""
    url = item.get("link") or item.get("guid") or ""
    title = strip_html(item.get("title"))
    desc = strip_html(item.get("description"))
    published = item.get("date") or item.get("published") or ""
    ent = extract_entities(title + " " + desc)
    return {
        "id": make_source_id("government", url),
        "type": "gov_policy",
        "actor_type": "government",
        "actor_name": "대한민국 정부(정책브리핑)",
        "title": title,
        "excerpt": desc[:300],    # KOGL 공공자료 짧은 발췌(AI 보강 입력용)
        "summary": None,          # Task 5에서 AI 채움
        "claim_summary": None,
        "position": None,
        "source_bias": "official",
        "url": url,
        "published_at": published,
        "entities": ent,
        "bill": None,
        "vote": None,
        "issue_id": None,
        "link_status": "new",     # 미연결 기본값(연결 쿼리 일관성 — Firestore None 매칭 회피)
    }


def normalize_bill(bill):
    """열린국회 법안 dict → source_item(assembly_bill)."""
    bill_id = str(bill.get("BILL_ID") or bill.get("bill_id") or "")
    name = bill.get("BILL_NAME") or bill.get("bill_name") or ""
    url = bill.get("DETAIL_LINK") or (
        f"https://likms.assembly.go.kr/bill/billDetail.do?billId={bill_id}" if bill_id else "")
    proposer = bill.get("PROPOSER") or bill.get("proposer") or ""
    return {
        "id": make_source_id("assembly", url),
        "type": "assembly_bill",
        "actor_type": "assembly",
        "actor_name": "국회",
        "title": name,
        "law_name": normalize_law_name(name),
        "procedural": is_procedural(name),
        "summary": None,
        "claim_summary": None,
        "position": "propose",
        "source_bias": "official",
        "url": url,
        "published_at": bill.get("PROPOSE_DT") or bill.get("propose_dt") or "",
        # bill_id(내부 PRC 해시) + BILL_NO(의안번호) 둘 다 — 정부/뉴스의 의안번호 언급과 매칭되도록
        "entities": {"people": [], "parties": [],
                     "bills": [b for b in [bill_id, str(bill.get("BILL_NO") or "").strip()] if b]},
        "bill": {
            "bill_id": bill_id,
            "bill_name": name,
            "proposers": [p.strip() for p in proposer.split(",") if p.strip()],
            "status": bill.get("PROC_RESULT") or bill.get("status") or "",
        },
        "vote": None,
        "issue_id": None,
        "link_status": "new",
    }


_VOTE_YES = ("찬성",)
_VOTE_NO = ("반대",)
_VOTE_ABS = ("기권",)


def normalize_vote(bill, vote_rows):
    """열린국회 표결 원자료(의원별 행 리스트) → assembly_vote source_item(집계)."""
    bill_id = str(bill.get("BILL_ID") or bill.get("bill_id") or "")
    name = bill.get("BILL_NAME") or bill.get("bill_name") or ""
    url = bill.get("BILL_URL") or bill.get("DETAIL_LINK") or (
        f"https://likms.assembly.go.kr/bill/billDetail.do?billId={bill_id}" if bill_id else "")
    yes = no = abstain = 0
    party = {}
    for v in (vote_rows or []):
        res = v.get("RESULT_VOTE_MOD") or v.get("VOTE_RESULT") or ""
        poly = v.get("POLY_NM") or "무소속"
        if any(k in res for k in _VOTE_YES):
            yes += 1
            party.setdefault(poly, {"yes": 0, "no": 0, "abstain": 0})["yes"] += 1
        elif any(k in res for k in _VOTE_NO):
            no += 1
            party.setdefault(poly, {"yes": 0, "no": 0, "abstain": 0})["no"] += 1
        elif any(k in res for k in _VOTE_ABS):
            abstain += 1
            party.setdefault(poly, {"yes": 0, "no": 0, "abstain": 0})["abstain"] += 1
    result = bill.get("PROC_RESULT") or ("가결" if yes > no else "부결" if no > yes else "")
    return {
        "id": make_source_id("assembly_vote", url + "#vote"),
        "type": "assembly_vote",
        "actor_type": "assembly",
        "actor_name": "국회 본회의",
        "title": f"표결: {name}",
        "law_name": normalize_law_name(name),
        "procedural": is_procedural(name),
        "summary": None,
        "claim_summary": None,
        "position": None,
        "source_bias": "official",
        "url": url,
        "published_at": bill.get("PROC_DT") or bill.get("VOTE_DATE") or "",
        "entities": {"people": [], "parties": list(party.keys()), "bills": [bill_id] if bill_id else []},
        "bill": None,
        "vote": {"bill_id": bill_id, "result": result, "yes": yes, "no": no,
                 "abstain": abstain, "party_breakdown": party},
        "issue_id": None,
        "link_status": "new",
    }
