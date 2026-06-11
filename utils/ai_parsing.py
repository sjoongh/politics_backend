"""AI 응답 파싱 순수 로직 (외부 의존 없음, 테스트 대상)."""
import json
import re


def extract_json_block(text):
    """LLM 텍스트 응답에서 첫 JSON 객체를 안전하게 추출. 실패 시 None."""
    if not text:
        return None
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    match = re.search(r"\{.*\}", cleaned, re.S)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except (json.JSONDecodeError, ValueError):
        return None
