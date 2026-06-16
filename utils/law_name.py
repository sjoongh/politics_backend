"""법안 제목 정규화 순수 로직 (테스트 대상). 법률명 추출 + 절차안 판정."""
import re

# 제거할 절차어(긴 것부터). '대안/수정안' 단독은 법률명 일부(대안학교 등) 훼손 위험이라
# 제외 — '(대안)'은 괄호 제거가 처리한다.
_PROC_TERMS = ["일부개정법률안", "전부개정법률안", "일부개정안", "전부개정안",
               "제정법률안", "개정법률안", "법률안", "개정안", "제정안"]
# 절차안 판정 플래그(괄호 포함 형태로 정확 매칭 — 일반어 오탐 줄임).
_PROC_FLAGS = ["(대안)", "(국토교통위원장)", "위원장)", "(의장)", "구성의 건", "위원 선임", "위원 선출"]
_PAREN = re.compile(r"\([^)]*\)")


def normalize_law_name(title):
    if not title:
        return ""
    t = _PAREN.sub("", title)            # 괄호 내용 제거
    t = t.replace("표결:", "")
    for term in _PROC_TERMS:
        t = t.replace(term, "")
    return re.sub(r"\s+", " ", t).strip()


def is_procedural(title):
    t = title or ""
    return any(f in t for f in _PROC_FLAGS)
