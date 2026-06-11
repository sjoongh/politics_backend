"""열린국회 OpenAPI 응답 envelope 파서 (외부 의존 없음, 테스트 대상)."""


def extract_rows(payload, service):
    """표준 envelope에서 row 리스트 추출. 오류/빈 응답이면 []."""
    if not isinstance(payload, dict):
        return []
    blocks = payload.get(service)
    if not isinstance(blocks, list):
        return []
    for block in blocks:
        if isinstance(block, dict) and "row" in block and isinstance(block["row"], list):
            return block["row"]
    return []
