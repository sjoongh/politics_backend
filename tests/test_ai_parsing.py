from utils.ai_parsing import extract_json_block


def test_plain_json():
    assert extract_json_block('{"ai_summary": "요약"}') == {"ai_summary": "요약"}


def test_markdown_fenced():
    txt = '```json\n{"a": 1, "b": "x"}\n```'
    assert extract_json_block(txt) == {"a": 1, "b": "x"}


def test_surrounding_text():
    txt = '다음은 결과입니다:\n{"status": "가결"}\n감사합니다.'
    assert extract_json_block(txt) == {"status": "가결"}


def test_invalid_json_returns_none():
    assert extract_json_block('{not valid}') is None
    assert extract_json_block('no json here') is None
    assert extract_json_block('') is None
    assert extract_json_block(None) is None
