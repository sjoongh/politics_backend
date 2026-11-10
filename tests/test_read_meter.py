from utils.read_meter import ReadMeter


class FakeDocRef:
    def get(self):
        return "snap"

    def set(self, v):
        return None

    def update(self, v):
        return None


class FakeQuery:
    def stream(self):
        yield from ("a", "b", "c")


class FakeClient:
    def get_all(self, refs):
        return ["x" for _ in refs]


def test_meter_counts_reads_and_writes():
    m = ReadMeter()
    m.install(doc_ref_cls=FakeDocRef, query_cls=FakeQuery, client_cls=FakeClient)
    try:
        FakeDocRef().get()
        FakeDocRef().get()
        FakeDocRef().update({})
        list(FakeQuery().stream())             # 3 docs = 3 reads
        list(FakeClient().get_all([1, 2]))     # 2 reads
        assert m.snapshot() == {"reads": 7, "writes": 1}
        m.reset()
        assert m.snapshot() == {"reads": 0, "writes": 0}
    finally:
        m.uninstall()
    FakeDocRef().get()
    assert m.snapshot() == {"reads": 0, "writes": 0}   # 제거 후에는 세지 않는다
