"""법안 제목 정규화 순수 로직 (테스트 대상). 법률명 추출 + 절차안 판정."""
import re

# 제거할 절차어(긴 것부터 — 부분 중복 방지).
_PROC_TERMS = ["일부개정법률안", "전부개정법률안", "일부개정안", "전부개정안",
               "제정법률안", "개정법률안", "법률안", "개정안", "제정안", "대안", "수정안"]
# 절차안(사건이 아니라 절차적 처리) 판정 플래그.
_PROC_FLAGS = ["대안", "위원장", "(의장)", "구성의 건", "위원 선임", "수정안", "선출"]
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
