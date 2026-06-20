"""뉴스 기사 엔티티/표현 추출 순수 로직 (테스트 대상).

한국 뉴스 제목은 핵심 쟁점을 따옴표(' ' " " ‘ ’ “ ” 「 」)로 감싼다 → 강한 phrase.
인물명은 외부에서 받은 known_names(의원 명단 등)로 매칭. 정당은 사전.
"""
import re

_PARTIES = ["더불어민주당", "국민의힘", "조국혁신당", "개혁신당", "진보당",
            "정의당", "기본소득당", "사회민주당", "민주당"]
# 따옴표 쌍: '...', "...", ‘...’, “...”, 「...」
_QUOTE = re.compile(r"[‘'\"“「]([^‘'\"“”’」]{2,30})[’'\"”」]")
_STOP_PHRASE = {"종합", "속보", "단독", "영상", "포토", "인터뷰"}


def normalize_phrase(s):
    return re.sub(r"\s+", " ", (s or "").strip())


def extract_phrases(text):
    """따옴표 안 핵심 표현(강한 신호) 추출."""
    out = []
    for m in _QUOTE.findall(text or ""):
        p = normalize_phrase(m)
        if len(p) >= 2 and p not in _STOP_PHRASE and p not in out:
            out.append(p)
    return out


def extract_entities(title, summary="", known_names=None):
    """기사 → {names, parties, phrases}. 인물은 known_names에서 텍스트에 등장하는 것."""
    known_names = known_names or set()
    blob = (title or "") + " " + (summary or "")
    names = sorted({n for n in known_names if n and n in blob})
    parties = []
    for p in _PARTIES:
        if p in blob and not any(p != o and p in o for o in parties):
            # 부분문자열 중복 방지(민주당 vs 더불어민주당)
            parties.append(p)
    parties = [p for p in parties if not any(p != o and p in o for o in parties)]
    phrases = extract_phrases(title or "")  # 제목 따옴표가 가장 강한 신호
    return {"names": names, "parties": sorted(set(parties)), "phrases": phrases}
