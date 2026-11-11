"""Firestore 읽기/쓰기 계측 — 파이프라인 실행당 읽기 수를 로그로 남기기 위한 몽키패치.
install()은 클래스 메서드를 감싸고 uninstall()로 원복한다. 운영 기본 대상은 google.cloud.firestore_v1의
DocumentReference / Query / Client 이며, 테스트는 가짜 클래스를 넘긴다."""


class ReadMeter:
    def __init__(self):
        self.reads = 0
        self.writes = 0
        self._patched = []

    def snapshot(self) -> dict:
        return {"reads": self.reads, "writes": self.writes}

    def reset(self) -> None:
        self.reads = self.writes = 0

    def _wrap(self, cls, name, kind):
        orig = getattr(cls, name, None)
        if orig is None:
            return
        meter = self

        if kind == "read1":
            def wrapped(self_, *a, **k):
                meter.reads += 1
                return orig(self_, *a, **k)
        elif kind == "write1":
            def wrapped(self_, *a, **k):
                meter.writes += 1
                return orig(self_, *a, **k)
        elif kind == "stream":
            def wrapped(self_, *a, **k):
                for item in orig(self_, *a, **k):
                    meter.reads += 1
                    yield item
        else:  # get_all
            def wrapped(self_, refs, *a, **k):
                refs = list(refs)
                meter.reads += len(refs)
                return orig(self_, refs, *a, **k)
        setattr(cls, name, wrapped)
        self._patched.append((cls, name, orig))

    def install(self, doc_ref_cls=None, query_cls=None, client_cls=None) -> None:
        if doc_ref_cls is None or query_cls is None or client_cls is None:
            from google.cloud.firestore_v1.document import DocumentReference
            from google.cloud.firestore_v1.query import Query
            from google.cloud.firestore_v1.client import Client
            doc_ref_cls = doc_ref_cls or DocumentReference
            query_cls = query_cls or Query
            client_cls = client_cls or Client
        self._wrap(doc_ref_cls, "get", "read1")
        self._wrap(doc_ref_cls, "set", "write1")
        self._wrap(doc_ref_cls, "update", "write1")
        self._wrap(doc_ref_cls, "delete", "write1")
        self._wrap(query_cls, "stream", "stream")
        self._wrap(client_cls, "get_all", "get_all")

    def uninstall(self) -> None:
        for cls, name, orig in reversed(self._patched):
            setattr(cls, name, orig)
        self._patched = []
