"""불투명 페이지 커서 (base64url JSON). 깨진 입력은 빈 dict → 첫 페이지로 처리."""
import base64
import json


def encode_cursor(d: dict) -> str:
    raw = json.dumps(d, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def valid_page_cursor(cur: dict, key_name: str) -> bool:
    """정렬값(key_name)은 숫자/문자열, 문서 id는 '/' 없는 문자열이어야 Firestore start_after에 안전하다."""
    if not isinstance(cur, dict) or key_name not in cur or "i" not in cur:
        return False
    k, i = cur[key_name], cur["i"]
    if isinstance(k, bool) or not isinstance(k, (int, float, str)):
        return False
    return isinstance(i, str) and bool(i) and "/" not in i


def decode_cursor(s) -> dict:
    if not s or not isinstance(s, str):
        return {}
    try:
        pad = "=" * (-len(s) % 4)
        obj = json.loads(base64.urlsafe_b64decode((s + pad).encode("ascii")).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, TypeError):
        return {}
    return obj if isinstance(obj, dict) else {}
