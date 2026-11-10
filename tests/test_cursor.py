from utils.cursor import encode_cursor, decode_cursor


def test_roundtrip():
    assert decode_cursor(encode_cursor({"o": 30})) == {"o": 30}


def test_garbage_is_empty():
    assert decode_cursor("!!notbase64") == {}


def test_none_is_empty():
    assert decode_cursor(None) == {}


def test_non_object_json_is_empty():
    import base64
    assert decode_cursor(base64.urlsafe_b64encode(b"[1,2]").decode()) == {}
