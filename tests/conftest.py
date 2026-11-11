"""CI(자격 증명 없음)에서 서비스 계층 테스트가 Firebase 초기화로 죽지 않도록 스텁 모듈을 주입한다.
테스트는 각 모듈의 `db`를 가짜 DB로 monkeypatch해서 쓴다. 로컬처럼 자격 증명이 있으면 아무것도 하지 않는다."""
import os
import sys
import types

if not os.getenv("FIREBASE_PRIVATE_KEY") and "firebase.firebase_config" not in sys.modules:
    stub = types.ModuleType("firebase.firebase_config")
    stub.db = None
    stub.firebase_auth = None
    stub.firebase_instance = None
    pkg = sys.modules.get("firebase") or types.ModuleType("firebase")
    pkg.firebase_config = stub
    if not hasattr(pkg, "__path__"):
        pkg.__path__ = [os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "firebase")]
    sys.modules["firebase"] = pkg
    sys.modules["firebase.firebase_config"] = stub
