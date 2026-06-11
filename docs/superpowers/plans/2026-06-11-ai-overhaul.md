# 슬라이스 1: AI 오버홀 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (inline). Steps use `- [ ]`.

**Goal:** AI 요약을 `gemini-2.5-flash`로 전환(빠름·저렴)하고, 재시도를 `success:False`에도 작동시키며, JSON 파싱을 견고화한다.

**Architecture:** `ai_service.py`의 모델/재시도/파싱을 개선. JSON 추출 로직은 firebase·gemini 비의존 순수 함수 `utils/ai_parsing.py`로 분리해 pytest로 검증. Gemini 실제 호출은 키 없어 코드/파싱까지만 검증.

**검증:** pytest(파싱 순수함수) + py_compile. 작업 전 `git checkout -b feat/ai-overhaul`. 디렉토리 `/Users/manager/side/politics_backend`.

---

## Task 1: JSON 추출 순수 함수 + 테스트

**Files:** Create `utils/ai_parsing.py`, `tests/test_ai_parsing.py`

- [ ] **Step 1: 실패 테스트 `tests/test_ai_parsing.py`**
```python
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
```

- [ ] **Step 2: 실패 확인** — `source .venv/bin/activate && python -m pytest tests/test_ai_parsing.py -v` → FAIL.

- [ ] **Step 3: `utils/ai_parsing.py` 구현** (firebase/gemini 비의존)
```python
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
```

- [ ] **Step 4: 통과 확인** — `python -m pytest tests/test_ai_parsing.py -v` → 4 passed.

- [ ] **Step 5: Commit**
```bash
git add utils/ai_parsing.py tests/test_ai_parsing.py
git commit -m "feat(ai): testable extract_json_block (markdown fences, invalid->None)"
```

---

## Task 2: ai_service 개선 (flash + retry + 파싱)

**Files:** Modify `services/ai_service.py`

- [ ] **Step 1: import 추가** — 상단 import에 추가:
```python
from utils.ai_parsing import extract_json_block
```

- [ ] **Step 2: 모델 env 설정 + flash 기본값** — `__init__` 의 모델 라인 교체:
```python
        genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.model = genai.GenerativeModel(self.model_name)
```

- [ ] **Step 3: 재시도를 success:False에도 작동** — `summarize_by_category` 전체 교체:
```python
    async def summarize_by_category(self, category, title, summary, max_retries=3):
        last = {"success": False, "message": "요약 실패"}
        for attempt in range(max_retries):
            try:
                result = await self.summarize_by_category2(category, title, summary)
                if result.get("success"):
                    return result
                last = result
            except Exception as e:
                last = {"success": False, "message": str(e)}
            if attempt < max_retries - 1:
                await asyncio.sleep(2 * (attempt + 1))
        return last
```

- [ ] **Step 4: JSON 파싱을 견고 함수로 교체** — `summarize_by_category2` 내 JSON 추출 블록(아래)을 교체:
기존:
```python
            # JSON 추출
            json_match = re.search(r"\{.*\}", raw_text, re.S)
            if not json_match:
                return {"success": False, "message": "AI 응답에서 JSON을 찾지 못함", "raw": raw_text}

            parsed_data = json.loads(json_match.group())
            return {"success": True, "data": parsed_data}
```
교체:
```python
            # JSON 추출 (견고)
            parsed_data = extract_json_block(raw_text)
            if parsed_data is None:
                return {"success": False, "message": "AI 응답에서 JSON 파싱 실패", "raw": raw_text}
            return {"success": True, "data": parsed_data}
```

- [ ] **Step 5: 문법 검증** — `python3 -m py_compile services/ai_service.py && echo ok`. (import 후 실제 호출은 Gemini 키 필요라 생략.)

- [ ] **Step 6: Commit**
```bash
git add services/ai_service.py
git commit -m "feat(ai): gemini-2.5-flash (env GEMINI_MODEL) + retry on soft-fail + robust JSON parse"
```

---

## Task 3: 전체 검증
- [ ] `source .venv/bin/activate && python -m pytest tests/ -q` → 모두 통과
- [ ] `python3 -m py_compile services/ai_service.py utils/ai_parsing.py main.py && echo ok`

## Self-Review
- 모델 flash 전환(T2-2), retry soft-fail(T2-3), 파싱 견고화(T1+T2-4). 프롬프트는 기능 영향 없어 유지.
- 순수 파싱 로직은 pytest로 실제 검증. Gemini 호출은 키 없어 코드까지만.

## 다음 슬라이스
2️⃣ 크롤링 오버홀(본문 크롤 + 중복체크 + 발언수집).
